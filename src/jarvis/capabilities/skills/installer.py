"""Installation/désinstallation des skills depuis jarvis-skills."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import httpx
from loguru import logger

from jarvis.capabilities.skills.registry import SKILLS_INSTALLED_DIR, skill_registry
from jarvis.kernel.paths import UI_STATIC_DIR

ENV_FILE = Path(".env")

SKILLS_REPO_RAW = "https://raw.githubusercontent.com/Grominet95/jarvis-skills/main"
SKILLS_INDEX_URL = f"{SKILLS_REPO_RAW}/index.json"

LOCAL_CATALOG = Path(__file__).parent / "catalog.json"


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
                static_dst = UI_STATIC_DIR / "skills" / skill_name
                static_dst.mkdir(parents=True, exist_ok=True)
                async with httpx.AsyncClient(timeout=15) as client:
                    for fname in static_files:
                        r = await client.get(f"{SKILLS_REPO_RAW}/{path}/static/{fname}")
                        if r.status_code == 200:
                            (static_dst / fname).write_bytes(r.content)
                        else:
                            logger.warning(
                                f"Fichier statique manquant : {fname} (HTTP {r.status_code})"
                            )

    async def _install_view(
        self, skill_name: str, skill_meta: dict, skill_dir: Path, path: str
    ) -> None:
        """Installe une vue.

        Stratégie :
        - Honore catalog.static_files (ex. globe-view : globe.js + globe.css)
        - Fallback : view.js (+ view.css optionnel)
        - skill.py : DL depuis GitHub s'il existe, sinon générique
        - skill.yaml : pareil
        ShowViewTool est un tool core (main.py), pas besoin de le fournir ici.
        """
        static_dst = UI_STATIC_DIR / "skills" / skill_name
        static_dst.mkdir(parents=True, exist_ok=True)
        catalog_files = skill_meta.get("static_files") or []
        targets = catalog_files if catalog_files else ["view.js", "view.css"]

        async with httpx.AsyncClient(timeout=15) as client:
            downloaded: list[str] = []
            for fname in targets:
                r = await client.get(f"{SKILLS_REPO_RAW}/{path}/{fname}")
                if r.status_code == 200:
                    (static_dst / fname).write_bytes(r.content)
                    downloaded.append(fname)
                elif not catalog_files and fname == "view.css":
                    continue  # view.css optionnel par défaut
                elif catalog_files:
                    logger.warning(f"Fichier {fname} manquant (HTTP {r.status_code})")
            if not downloaded:
                raise Exception("Aucun asset de vue téléchargé")

            # skill.py custom prioritaire (ex. globe-view)
            r = await client.get(f"{SKILLS_REPO_RAW}/{path}/skill.py")
            has_remote_skill_py = r.status_code == 200
            if has_remote_skill_py:
                (skill_dir / "skill.py").write_text(r.text)

            r = await client.get(f"{SKILLS_REPO_RAW}/{path}/skill.yaml")
            has_remote_yaml = r.status_code == 200
            if has_remote_yaml:
                (skill_dir / "skill.yaml").write_text(r.text)

        if not has_remote_skill_py:
            class_name = "".join(w.capitalize() for w in skill_name.replace("-", "_").split("_"))
            description = skill_meta.get("description", "")
            view_id = skill_meta.get("view_id", skill_name)
            skill_py = (
                "from skills.base import SkillBase\n\n\n"
                f"class {class_name}Skill(SkillBase):\n"
                f"    SYSTEM_PROMPT = (\n"
                f'        "Vue \\"{view_id}\\" : {description}\\n"\n'
                f'        "Afficher : show_view(action=\\"show\\", view_id=\\"{view_id}\\").\\n"\n'
                f'        "Masquer : show_view(action=\\"hide\\", view_id=\\"{view_id}\\").\\n"\n'
                f'        "\\n"\n'
                f'        "RÈGLE : quand cette vue est ouverte, NE PAS utiliser fly_to "\n'
                f'        "(réservé au globe terrestre). Si la vue expose des commandes "\n'
                f'        "spécifiques, les invoquer via "\n'
                f'        "show_view(action=\\"view_command\\", view_id=\\"{view_id}\\", "\n'
                f'        "command=..., params={{...}})."\n'
                f"    )\n\n"
                "    def get_tools(self) -> list:\n"
                "        return []\n"
            )
            (skill_dir / "skill.py").write_text(skill_py)

        if not has_remote_yaml:
            import yaml

            yaml_meta = {
                "name": skill_name,
                "label": skill_meta.get("label", skill_name),
                "version": skill_meta.get("version", "1.0.0"),
                "author": skill_meta.get("author", ""),
                "description": skill_meta.get("description", ""),
                "tags": skill_meta.get("tags", ["view"]),
                "type": "view",
                "static_files": downloaded,
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
            static_dst = UI_STATIC_DIR / "skills" / skill_name
            if static_dst.exists():
                shutil.rmtree(static_dst)
                logger.debug(f"Fichiers statiques supprimés pour {skill_name}")
            skill_registry.reload()
            logger.info(f"Skill désinstallé : {skill_name}")
            return {"success": True, "message": f"Skill '{skill_name}' désinstallé"}
        except Exception as e:
            return {"success": False, "message": str(e)}


skill_installer = SkillInstaller()
