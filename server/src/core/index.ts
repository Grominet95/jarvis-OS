import { EventEmitter } from 'node:events'

import {
  HOST,
  PORT,
  PYTHON_TCP_SERVER_HOST,
  PYTHON_TCP_SERVER_PORT,
  PYTHON_TCP_SERVER_LD_LIBRARY_PATH
} from '@/constants'
import TCPClient from '@/core/tcp-client'
import HTTPServer from '@/core/http-server/http-server'
import SocketServer from '@/core/socket-server'
import SpeechToText from '@/core/stt/stt'
import TextToSpeech from '@/core/tts/tts'
import AutomaticSpeechRecognition from '@/core/asr/asr'
import NamedEntityRecognition from '@/core/nlp/nlu/ner'
import ModelLoader from '@/core/nlp/nlu/model-loader'
import NaturalLanguageUnderstanding from '@/core/nlp/nlu/nlu'
import Brain from '@/core/brain/brain'
import LLMManager from '@/core/llm-manager/llm-manager'
import LLMProvider from '@/core/llm-manager/llm-provider'
import Persona from '@/core/llm-manager/persona'
import { ConversationLogger } from '@/conversation-logger'
import { SystemHelper } from '@/helpers/system-helper'
import { LogHelper } from '@/helpers/log-helper'

/**
 * Set environment variables
 */

if (SystemHelper.isLinux()) {
  process.env['LD_LIBRARY_PATH'] = PYTHON_TCP_SERVER_LD_LIBRARY_PATH
  LogHelper.info(`LD_LIBRARY_PATH set to: ${process.env['LD_LIBRARY_PATH']}`)
}

/**
 * Register core nodes
 */

export const PYTHON_TCP_CLIENT = new TCPClient(
  'Python',
  String(PYTHON_TCP_SERVER_HOST),
  PYTHON_TCP_SERVER_PORT
)

export const EVENT_EMITTER = new EventEmitter()

/**
 * Register core singletons
 */

export const LLM_PROVIDER = new LLMProvider()

export const LLM_MANAGER = new LLMManager()

export const CONVERSATION_LOGGER = new ConversationLogger({
  loggerName: 'Conversation Logger',
  fileName: 'conversation_log.json',
  nbOfLogsToKeep: 512,
  nbOfLogsToLoad: 96
})
export const LOOP_CONVERSATION_LOGGER = new ConversationLogger({
  loggerName: 'Loop Conversation Logger',
  fileName: 'loop_conversation_log.json',
  nbOfLogsToKeep: 512,
  nbOfLogsToLoad: 96
})

export const HTTP_SERVER = new HTTPServer(String(HOST), PORT)

export const SOCKET_SERVER = new SocketServer()

export const PERSONA = new Persona()

export const STT = new SpeechToText()

export const TTS = new TextToSpeech()

export const ASR = new AutomaticSpeechRecognition()

export const NER = new NamedEntityRecognition()

export const MODEL_LOADER = new ModelLoader()

export const NLU = new NaturalLanguageUnderstanding()

export const BRAIN = new Brain()
