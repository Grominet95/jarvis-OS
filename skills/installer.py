"""Installation/désinstallation des skills depuis jarvis-skills."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import httpx
from loguru import logger

from skills.registry import SKILLS_INSTALLED_DIR, skill_registry

ENV_FILE = Path(".env")

SKILLS_REPO_RAW = "https://raw.githubusercontent.com/Grominet95/jarvis-skills/main"
SKILLS_INDEX_URL = f"{SKILLS_REPO_RAW}/index.json"

LOCAL_CATALOG = Path("skills/catalog.json")


class SkillInstaller:
    def _inject_env_vars(self, requires_env: list[str], skill_name: str) -> None:
        """Ajoute les variables requires_env manquantes dans .env avec valeur vide."""
        from dotenv import dotenv_values, set_key

        existing = dotenv_values(str(ENV_FILE)) if ENV_FILE.exists() else {}
        for key in requires_env:
            if key not in existing:
                set_key(str(ENV_FILE), key, "")
                logger.debug(f"Env var ajoutée pour {skill_name}: {key}")

    async def fetch_catalog(self) -> list[dict]:
        """
        Récupère le catalogue depuis GitHub.
        Fallback sur le catalogue local si inaccessible.
        """
        offline = False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(SKILLS_INDEX_URL)
                if r.status_code == 200:
                    data = r.json()
                    skills = data.get("skills", [])
                    for s in skills:
                        s.setdefault("type", "conversational")
                    presets = data.get("presets", [])
                    for p in presets:
                        p.setdefault("type", "preset")
                    views = data.get("views", [])
                    for v in views:
                        v.setdefault("type", "view")
                    all_items = skills + presets + views
                else:
                    raise Exception(f"HTTP {r.status_code}")
        except Exception as e:
            logger.warning(f"Catalogue GitHub inaccessible: {e} — fallback local")
            all_items = self._load_local_catalog()
            offline = True

        installed = {s["name"] for s in skill_registry.list_installed()}
        for item in all_items:
            item["installed"] = item["name"] in installed
            item["offline"] = offline

        return all_items

    def _load_local_catalog(self) -> list[dict]:
        if not LOCAL_CATALOG.exists():
            return []
        data = json.loads(LOCAL_CATALOG.read_text())
        skills = data.get("skills", [])
        for s in skills:
            s.setdefault("type", "conversational")
        presets = data.get("presets", [])
        for p in presets:
            p.setdefault("type", "preset")
        views = data.get("views", [])
        for v in views:
            v.setdefault("type", "view")
        return skills + presets + views

    async def install(self, skill_name: str) -> dict:
        """Télécharge et installe un skill/preset/vue depuis GitHub."""
        catalog = await self.fetch_catalog()
        skill_meta = next((s for s in catalog if s["name"] == skill_name), None)

        if not skill_meta:
            return {
                "success": False,
                "message": f"'{skill_name}' introuvable dans le catalogue",
            }

        item_type = skill_meta.get("type", "conversational")
        skill_dir = SKILLS_INSTALLED_DIR / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_meta.get("path", f"skills/{skill_name}")

        try:
            if item_type == "view":
                await self._install_view(skill_name, skill_meta, skill_dir, path)
            else:
                await self._install_skill(skill_name, skill_meta, skill_dir, path)

            skill_registry.reload()
            logger.info(f"Installé ({item_type}) : {skill_name}")
            return {"success": True, "message": f"'{skill_name}' installé avec succès"}

        except Exception as e:
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
            logger.error(f"Erreur installation {skill_name}: {e}")
            return {"success": False, "message": str(e)}

    async def _install_skill(
        self, skill_name: str, skill_meta: dict, skill_dir: Path, path: str
    ) -> None:
        """Installe un skill ou preset (skill.py + skill.yaml depuis GitHub)."""
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{SKILLS_REPO_RAW}/{path}/skill.py")
            if r.status_code != 200:
                raise Exception(f"skill.py introuvable (HTTP {r.status_code})")
            (skill_dir / "skill.py").write_text(r.text)

            r = await client.get(f"{SKILLS_REPO_RAW}/{path}/skill.yaml")
            if r.status_code == 200:
                (skill_dir / "skill.yaml").write_text(r.text)

        yaml_path = skill_dir / "skill.yaml"
        if yaml_path.exists():
            import yaml

            with yaml_path.open() as f:
                meta = yaml.safe_load(f) or {}
            requires_env = meta.get("requires_env", [])
            if requires_env:
                self._inject_env_vars(requires_env, skill_name)

            static_files = meta.get("static_files", [])
            if static_files:
                static_dst = Path("ui/static/skills") / skill_name
                static_dst.mkdir(parents=True, exist_ok=True)
                async with httpx.AsyncClient(timeout=15) as client:
                    for fname in static_files:
                        r = await client.get(f"{SKILLS_REPO_RAW}/{path}/static/{fname}")
                        if r.status_code == 200:
                            (static_dst / fname).write_bytes(r.content)
                        else:
                            logger.warning(f"Fichier statique manquant : {fname} (HTTP {r.status_code})")

    async def _install_view(
        self, skill_name: str, skill_meta: dict, skill_dir: Path, path: str
    ) -> None:
        """Installe une vue (view.js + view.css optionnel, skill.py généré localement)."""
        static_dst = Path("ui/static/skills") / skill_name
        static_dst.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=15) as client:
            # Télécharge view.js (obligatoire)
            r = await client.get(f"{SKILLS_REPO_RAW}/{path}/view.js")
            if r.status_code != 200:
                raise Exception(f"view.js introuvable (HTTP {r.status_code})")
            (static_dst / "view.js").write_text(r.text)

            # Télécharge view.css si présent
            r = await client.get(f"{SKILLS_REPO_RAW}/{path}/view.css")
            if r.status_code == 200:
                (static_dst / "view.css").write_text(r.text)

        # Génère skill.py : SYSTEM_PROMPT uniquement, pas de tool dupliqué
        # (ShowViewTool est déjà enregistré par globe-view et accepte n'importe quel view_id)
        class_name = "".join(w.capitalize() for w in skill_name.replace("-", "_").split("_"))
        description = skill_meta.get("description", "")
        view_id = skill_name  # convention : view_id == skill_name
        skill_py = (
            "from skills.base import SkillBase\n\n\n"
            f"class {class_name}Skill(SkillBase):\n"
            f'    SYSTEM_PROMPT = (\n'
            f'        "Vue \\"{view_id}\\" installée : {description} "\n'
            f'        "Pour l\'afficher : show_view(action=\\"show\\", view_id=\\"{view_id}\\"). "\n'
            f'        "Pour la masquer : show_view(action=\\"hide\\", view_id=\\"{view_id}\\")."\n'
            f'    )\n\n'
            "    def get_tools(self) -> list:\n"
            "        return []\n"
        )
        (skill_dir / "skill.py").write_text(skill_py)

        # Génère skill.yaml depuis les métadonnées du catalogue
        import yaml

        static_files = []
        if (static_dst / "view.js").exists():
            static_files.append("view.js")
        if (static_dst / "view.css").exists():
            static_files.append("view.css")

        yaml_meta = {
            "name": skill_name,
            "label": skill_meta.get("label", skill_name),
            "version": skill_meta.get("version", "1.0.0"),
            "author": skill_meta.get("author", ""),
            "description": skill_meta.get("description", ""),
            "tags": skill_meta.get("tags", ["view"]),
            "type": "view",
            "static_files": static_files,
            "requires_env": [],
            "requires_tools": [],
            "capabilities": skill_meta.get("capabilities", []),
        }
        (skill_dir / "skill.yaml").write_text(yaml.dump(yaml_meta, allow_unicode=True))

    def uninstall(self, skill_name: str) -> dict:
        """Désinstalle un skill."""
        skill_dir = SKILLS_INSTALLED_DIR / skill_name

        if not skill_dir.exists():
            return {"success": False, "message": f"Skill '{skill_name}' n'est pas installé"}

        try:
            shutil.rmtree(skill_dir)
            # Supprimer les fichiers statiques s'il y en a
            static_dst = Path("ui/static/skills") / skill_name
            if static_dst.exists():
                shutil.rmtree(static_dst)
                logger.debug(f"Fichiers statiques supprimés pour {skill_name}")
            skill_registry.reload()
            logger.info(f"Skill désinstallé : {skill_name}")
            return {"success": True, "message": f"Skill '{skill_name}' désinstallé"}
        except Exception as e:
            return {"success": False, "message": str(e)}


skill_installer = SkillInstaller()
