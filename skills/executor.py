"""Exécuteur de routines Jarvis — gère l'exécution step par step."""
from __future__ import annotations

import asyncio
import platform
from loguru import logger

from skills.base import RoutineSkill, RoutineStep


class RoutineExecutor:
    """
    Exécute une routine step par step.
    Types supportés : cli, spotify, tts, ai, wait, notify
    """

    def __init__(self, tool_registry=None, tts_engine=None, llm_client=None):
        self._tools = tool_registry
        self._tts = tts_engine
        self._llm = llm_client

    async def execute(self, routine: RoutineSkill, broadcast_fn=None) -> dict:
        """
        Exécute tous les steps d'une routine.
        broadcast_fn : coroutine async(dict) pour envoyer des events WebSocket.
        """
        steps = routine.get_steps()
        results = {
            "routine": routine.name,
            "success": True,
            "steps_done": 0,
            "steps_skipped": 0,
            "steps_failed": 0,
            "logs": [],
        }

        logger.info(f"Routine '{routine.name}' — démarrage ({len(steps)} steps)")

        if broadcast_fn:
            await broadcast_fn({
                "type": "routine_started",
                "routine": routine.name,
                "label": routine.label,
                "total_steps": len(steps),
            })

        for i, step in enumerate(steps):
            step_result = await self._execute_step(step, i + 1, len(steps))

            results["logs"].append({
                "step": step.name,
                "type": step.type,
                "status": step_result["status"],
                "message": step_result.get("message", ""),
            })

            if step_result["status"] == "done":
                results["steps_done"] += 1
            elif step_result["status"] == "skipped":
                results["steps_skipped"] += 1
            elif step_result["status"] == "failed":
                results["steps_failed"] += 1

            if broadcast_fn:
                await broadcast_fn({
                    "type": "routine_step",
                    "routine": routine.name,
                    "step_index": i + 1,
                    "step_name": step.name,
                    "step_type": step.type,
                    "status": step_result["status"],
                })

        if broadcast_fn:
            await broadcast_fn({
                "type": "routine_finished",
                "routine": routine.name,
                "results": results,
            })

        logger.info(
            f"Routine '{routine.name}' terminée — "
            f"{results['steps_done']} ✓ "
            f"{results['steps_skipped']} skipped "
            f"{results['steps_failed']} ✗"
        )

        return results

    async def _execute_step(self, step: RoutineStep, index: int, total: int) -> dict:
        logger.debug(f"Step {index}/{total} [{step.type}] : {step.name}")

        handlers = {
            "cli": self._exec_cli,
            "spotify": self._exec_spotify,
            "tts": self._exec_tts,
            "ai": self._exec_ai,
            "wait": self._exec_wait,
            "notify": self._exec_notify,
        }

        handler = handlers.get(step.type)
        if not handler:
            return {"status": "skipped", "message": f"Type de step inconnu : {step.type}"}

        try:
            return await handler(step)
        except Exception as e:
            logger.error(f"Erreur step '{step.name}': {e}")
            return {"status": "failed", "message": str(e)}

    async def _exec_cli(self, step: RoutineStep) -> dict:
        cmd = step.get_command()

        if cmd is None:
            system = platform.system().lower()
            return {"status": "skipped", "message": f"Non supporté sur {system}"}

        logger.debug(f"CLI : {cmd[:80]}")

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode == 0:
            return {"status": "done", "message": stdout.decode()[:200]}
        return {"status": "failed", "message": stderr.decode()[:200]}

    async def _exec_spotify(self, step: RoutineStep) -> dict:
        if not self._tools:
            return {"status": "skipped", "message": "ToolRegistry non disponible"}

        result = await self._tools.call(
            "spotify_control",
            {"action": step.action or "play", "query": step.query or ""},
        )

        if not result.is_error:
            return {"status": "done", "message": result.content}
        return {"status": "failed", "message": result.content}

    async def _exec_tts(self, step: RoutineStep) -> dict:
        if not self._tts or not step.text:
            return {"status": "skipped", "message": "TTS non disponible ou texte vide"}

        audio_bytes = await self._tts.synthesize(step.text)

        from background.notifications import broadcast_audio
        await broadcast_audio(audio_bytes)

        return {"status": "done", "message": f"TTS : {step.text[:50]}"}

    async def _exec_ai(self, step: RoutineStep) -> dict:
        if not self._llm or not step.prompt:
            return {"status": "skipped", "message": "LLM non disponible ou prompt vide"}

        response = await self._llm.complete(
            messages=[{"role": "user", "content": step.prompt}],
            max_tokens=150,
            system="Tu es Jarvis. Réponds de façon courte et naturelle, en français.",
        )

        text = response.content if hasattr(response, "content") else str(response)

        if self._tts and text:
            audio_bytes = await self._tts.synthesize(text)
            from background.notifications import broadcast_audio
            await broadcast_audio(audio_bytes)

        return {"status": "done", "message": text[:100]}

    async def _exec_wait(self, step: RoutineStep) -> dict:
        seconds = max(0, min(step.seconds, 30))
        await asyncio.sleep(seconds)
        return {"status": "done", "message": f"Attente {seconds}s"}

    async def _exec_notify(self, step: RoutineStep) -> dict:
        cmd = step.get_command()

        if not cmd:
            system = platform.system().lower()
            if system == "darwin":
                title = step.title.replace('"', '\\"')
                body = step.body.replace('"', '\\"')
                cmd = (
                    f"osascript -e 'display notification "
                    f'"{body}" with title "{title}"' + "'"
                )
            elif system == "windows":
                cmd = (
                    f"powershell -c \"Add-Type -AssemblyName System.Windows.Forms; "
                    f"[System.Windows.Forms.MessageBox]::Show('{step.body}','{step.title}')\""
                )
            else:
                return {"status": "skipped", "message": "Notifications non supportées sur Linux"}

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        return {"status": "done", "message": f"Notification : {step.title}"}
