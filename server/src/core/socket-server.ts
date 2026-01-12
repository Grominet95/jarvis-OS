import type { DefaultEventsMap } from 'socket.io/dist/typed-events'
import { Server as SocketIOServer, Socket } from 'socket.io'
import axios from 'axios'

import {
  LANG,
  HAS_STT,
  HAS_TTS,
  IS_DEVELOPMENT_ENV,
  API_VERSION
} from '@/constants'
import {
  HTTP_SERVER,
  PYTHON_TCP_CLIENT,
  ASR,
  STT,
  TTS,
  NLU,
  BRAIN,
  MODEL_LOADER,
  LLM_MANAGER
} from '@/core'
import { LogHelper } from '@/helpers/log-helper'
import { LangHelper } from '@/helpers/lang-helper'
import { Telemetry } from '@/telemetry'

interface HotwordDataEvent {
  hotword: string
  buffer: Buffer
}

interface UtteranceDataEvent {
  client: string
  value: string
}

interface WidgetDataEvent {
  method: {
    methodName: string
    methodParams: Record<string, string | number | undefined | unknown[]>
  }
  // Data returned from Aurora components
  data: Record<string, string | number | undefined | unknown[]>
}

export default class SocketServer {
  private static instance: SocketServer

  public socket: Socket<DefaultEventsMap, DefaultEventsMap> | undefined =
    undefined

  constructor() {
    if (!SocketServer.instance) {
      LogHelper.title('Socket Server')
      LogHelper.success('New instance')

      SocketServer.instance = this
    }
  }

  public async init(): Promise<void> {
    const io = IS_DEVELOPMENT_ENV
      ? new SocketIOServer(HTTP_SERVER.httpServer, {
          cors: { origin: `${HTTP_SERVER.host}:3000` }
        })
      : new SocketIOServer(HTTP_SERVER.httpServer)

    let sttState = 'disabled'
    let ttsState = 'disabled'

    if (HAS_STT) {
      sttState = 'enabled'

      await STT.init()
    }
    if (HAS_TTS) {
      ttsState = 'enabled'

      await TTS.init(LangHelper.getShortCode(LANG))
    }

    LogHelper.title('Initialization')
    LogHelper.success(`STT ${sttState}`)
    LogHelper.success(`TTS ${ttsState}`)

    try {
      await MODEL_LOADER.loadNLPModels()
    } catch (e) {
      LogHelper.error(`Failed to load NLP models: ${e}`)
    }

    io.on('connection', (socket) => {
      LogHelper.title('Client')
      LogHelper.success('Connected')

      this.socket = socket

      // Init
      this.socket.on('init', async (data: string) => {
        LogHelper.info(`Type: ${data}`)
        LogHelper.info(`Socket ID: ${this.socket?.id}`)

        this.socket?.emit('init-client-core-server-handshake', 'success')

        // TODO
        // const provider = await addProvider(socket.id)

        // Check whether the Python TCP client is connected to the Python TCP server
        if (PYTHON_TCP_CLIENT.isConnected) {
          this.socket?.emit('ready')
          this.socket?.emit('init-tcp-server-boot', 'success')
        } else {
          PYTHON_TCP_CLIENT.ee.on('connected', () => {
            this.socket?.emit('ready')
            this.socket?.emit('init-tcp-server-boot', 'success')
          })
        }

        if (LLM_MANAGER.isLLMEnabled) {
          this.socket?.emit('init-llm', 'success')
        }

        if (LLM_MANAGER.shouldWarmUpLLMDuties) {
          if (!LLM_MANAGER.areLLMDutiesWarmedUp) {
            const interval = setInterval(() => {
              if (LLM_MANAGER.areLLMDutiesWarmedUp) {
                clearInterval(interval)
                this.socket?.emit('warmup-llm-duties', 'success')
              }
            }, 2_000)
          } else {
            this.socket?.emit('warmup-llm-duties', 'success')
          }
        }

        if (data === 'hotword-node') {
          // Hotword triggered
          this.socket?.on('hotword-detected', (data: HotwordDataEvent) => {
            LogHelper.title('Socket')
            LogHelper.success(`Hotword ${data.hotword} detected`)

            this.socket?.broadcast.emit('enable-record')
          })
        } else {
          // Listen for new utterance
          this.socket?.on('utterance', async (data: UtteranceDataEvent) => {
            LogHelper.title('Socket')
            LogHelper.info(`${data.client} emitted: ${data.value}`)

            this.socket?.emit('is-typing', true)

            const { value: utterance } = data
            try {
              LogHelper.time('Utterance processed in')

              // Always interrupt Leon's voice on answer
              BRAIN.setIsTalkingWithVoice(false, { shouldInterrupt: true })

              BRAIN.isMuted = false
              const processedData = await NLU.process(utterance)

              if (processedData) {
                Telemetry.utterance(processedData)
              }

              LogHelper.title('Execution Time')
              LogHelper.timeEnd('Utterance processed in')
            } catch (e) {
              LogHelper.error(`Failed to process utterance: ${e}`)
            }
          })

          // Handle new local ASR engine recording
          this.socket?.on('asr-start-record', () => {
            PYTHON_TCP_CLIENT.emit('asr_start_recording', null)
          })

          // Handle automatic speech recognition
          this.socket?.on('recognize', async (data: Buffer) => {
            try {
              await ASR.encode(data)
            } catch (e) {
              LogHelper.error(
                `ASR - Failed to encode audio blob to WAVE file: ${e}`
              )
            }
          })

          // Listen for widget events
          this.socket?.on('widget-event', async (event: WidgetDataEvent) => {
            LogHelper.title('Socket')
            LogHelper.info(`Widget event: ${JSON.stringify(event)}`)

            this.socket?.emit('is-typing', true)

            try {
              const { method } = event

              if (method.methodName === 'send_utterance') {
                const utterance = method.methodParams['utterance']

                if (method.methodParams['from'] === 'leon') {
                  await BRAIN.talk(utterance as string, true)
                } else {
                  this.socket?.emit('widget-send-utterance', utterance)
                }
              } else if (method.methodName === 'run_skill_action') {
                const { actionName, params } = method.methodParams

                await axios.post(
                  `${HTTP_SERVER.host}:${HTTP_SERVER.port}/api/${API_VERSION}/run-action`,
                  {
                    skill_action: actionName,
                    action_params: params
                  }
                )
              }
            } catch (e) {
              // eslint-disable-next-line @typescript-eslint/ban-ts-comment
              // @ts-expect-error
              LogHelper.error(`Failed to handle widget event: ${e.errors || e}`)
            } finally {
              this.socket?.emit('is-typing', false)
            }
          })
        }
      })

      this.socket.once('disconnect', () => {
        // TODO
        // deleteProvider(this.socket.id)
      })
    })
  }
}
