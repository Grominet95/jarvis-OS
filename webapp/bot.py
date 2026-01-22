#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipecat Quickstart Example.

The example runs a simple voice AI bot that you can connect to using your
browser and speak with it. You can also deploy this bot to Pipecat Cloud.

Required AI services:
- Deepgram (Speech-to-Text)
- OpenAI (LLM)
- Cartesia (Text-to-Speech)

Run the bot using::

    uv run bot.py
"""

import os
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
from loguru import logger

print("Starting Pipecat bot...")
print("Loading models and imports (20 seconds, first run only)\n")

logger.info("Loading Local Smart Turn Analyzer V3...")
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3

logger.info("Local Smart Turn Analyzer V3 loaded")
logger.info("Loading Silero VAD model...")
from pipecat.audio.vad.silero import SileroVADAnalyzer

logger.info("Silero VAD model loaded")

from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame

logger.info("Loading pipeline components...")
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams

DAILY_AVAILABLE = False
DailyParams = None

if sys.platform != "win32":
    try:
        from pipecat.transports.daily.transport import DailyParams
        DAILY_AVAILABLE = True
    except (ImportError, Exception):
        pass

from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import (
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies

logger.info("All components loaded successfully!")

load_dotenv(override=True)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    cartesia_key = os.getenv("CARTESIA_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not deepgram_key:
        logger.warning("DEEPGRAM_API_KEY not set, STT service will not work")
        print("[BOT] WARNING: DEEPGRAM_API_KEY not configured")
    if not cartesia_key:
        logger.warning("CARTESIA_API_KEY not set, TTS service will not work")
        print("[BOT] WARNING: CARTESIA_API_KEY not configured")
    if not openai_key:
        logger.warning("OPENAI_API_KEY not set, LLM service will not work")
        print("[BOT] WARNING: OPENAI_API_KEY not configured")

    stt = DeepgramSTTService(api_key=deepgram_key) if deepgram_key else None

    tts = CartesiaTTSService(
        api_key=cartesia_key,
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",
    ) if cartesia_key else None

    system_message = "Tu es l'assistant Jarvis personnel de Maxime. Tu parles UNIQUEMENT en français. Maxime parle aussi français. Tu es là pour l'aider dans ses tâches quotidiennes. Ne dis jamais bonjour ou présente-toi automatiquement, attends que Maxime te parle d'abord."
    
    llm = OpenAILLMService(
        api_key=openai_key,
        model="gpt-4o-mini"
    ) if openai_key else None
    
    if not llm:
        logger.error("Cannot start bot without OpenAI API key")
        print("[BOT] ERROR: Cannot start bot without OpenAI API key. Please configure it in settings.")
        raise ValueError("OpenAI API key is required to start the bot")
    
    logger.info(f"OpenAI LLM service initialized")

    messages = [
        {
            "role": "system",
            "content": system_message,
        },
    ]

    context = LLMContext(messages)
    print(f"[BOT] LLM context initialized with {len(messages)} messages")
    print(f"[BOT] System message: {system_message}")
    logger.info(f"LLM context initialized with {len(messages)} messages")
    logger.info(f"System message: {system_message}")
    
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]
            ),
        ),
    )
    
    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message):
        print(f"[BOT] [ASSISTANT] {message.content}")
        logger.info(f"[ASSISTANT] {message.content}")
        current_messages = context.get_messages() if hasattr(context, 'get_messages') else (context.messages if hasattr(context, 'messages') else [])
        print(f"[BOT] [ASSISTANT] Context has {len(current_messages)} messages")
        logger.info(f"[ASSISTANT] Context has {len(current_messages)} messages")
        if current_messages:
            print(f"[BOT] [ASSISTANT] First message role: {current_messages[0].get('role', 'unknown')}")
            logger.info(f"[ASSISTANT] First message role: {current_messages[0].get('role', 'unknown')}")
            if current_messages[0].get('role') == 'system':
                print(f"[BOT] [ASSISTANT] System message: {current_messages[0].get('content', '')[:100]}")
                logger.info(f"[ASSISTANT] System message: {current_messages[0].get('content', '')[:100]}")
    
    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, strategy, message):
        print(f"[BOT] [USER] {message.content}")
        logger.info(f"[USER] {message.content}")

    rtvi = RTVIProcessor()

    pipeline_components = [
        transport.input(),
        rtvi,
    ]
    
    if stt:
        pipeline_components.append(stt)
    
    pipeline_components.append(user_aggregator)
    pipeline_components.append(llm)
    
    if tts:
        pipeline_components.append(tts)
    
    pipeline_components.extend([
        transport.output(),
        assistant_aggregator,
    ])

    pipeline = Pipeline(pipeline_components)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        print(f"[BOT] Client connected - resetting context")
        try:
            if hasattr(context, 'messages'):
                print(f"[BOT] Context.messages before clear: {len(context.messages)} messages")
                for i, msg in enumerate(context.messages):
                    print(f"[BOT] Message {i}: role={msg.get('role', 'unknown')}, content={str(msg.get('content', ''))[:80]}")
                
                context.messages.clear()
                context.messages.append({"role": "system", "content": system_message})
                print(f"[BOT] Context reset with system message")
                print(f"[BOT] Context now has {len(context.messages)} messages")
                print(f"[BOT] First message: role={context.messages[0].get('role')}, content={context.messages[0].get('content', '')[:80]}")
                logger.info(f"Context reset with system message: {system_message[:50]}...")
            else:
                print(f"[BOT] Context does not have 'messages' attribute")
                logger.warn("Context does not have 'messages' attribute")
        except Exception as e:
            print(f"[BOT] Error resetting context: {e}")
            logger.error(f"Error resetting context: {e}")
            import traceback
            logger.error(traceback.format_exc())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point for the bot starter."""

    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    }

    if DAILY_AVAILABLE:
        transport_params["daily"] = lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        )

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
