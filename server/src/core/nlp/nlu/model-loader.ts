import fs from 'node:fs'

import { containerBootstrap } from '@nlpjs/core-loader'
import { Nlp } from '@nlpjs/nlp'
import { BuiltinMicrosoft } from '@nlpjs/builtin-microsoft'
import { LangAll } from '@nlpjs/lang-all'

import {
  MAIN_NLP_MODEL_PATH,
  GLOBAL_RESOLVERS_NLP_MODEL_PATH,
  SKILLS_RESOLVERS_NLP_MODEL_PATH
} from '@/constants'
import { MICROSOFT_BUILT_IN_ENTITIES } from '@/core/nlp/nlu/ner'
import { LogHelper } from '@/helpers/log-helper'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type NLPContainer = undefined | any

export default class ModelLoader {
  private static instance: ModelLoader
  public mainNLPContainer: NLPContainer
  public globalResolversNLPContainer: NLPContainer
  public skillsResolversNLPContainer: NLPContainer

  constructor() {
    if (!ModelLoader.instance) {
      LogHelper.title('Model Loader')
      LogHelper.success('New instance')

      ModelLoader.instance = this
    }
  }

  /**
   * Check if NLP models exists
   */
  public hasNlpModels(): boolean {
    return (
      !!this.globalResolversNLPContainer &&
      !!this.skillsResolversNLPContainer &&
      !!this.mainNLPContainer
    )
  }

  /**
   * Load all NLP models at once
   */
  public loadNLPModels(): Promise<[void, void, void]> {
    return Promise.all([
      this.loadGlobalResolversModel(GLOBAL_RESOLVERS_NLP_MODEL_PATH),
      this.loadSkillsResolversModel(SKILLS_RESOLVERS_NLP_MODEL_PATH),
      this.loadMainModel(MAIN_NLP_MODEL_PATH)
    ])
  }

  /**
   * Load the global resolvers NLP model from the latest training
   */
  private loadGlobalResolversModel(modelPath: string): Promise<void> {
    return new Promise(async (resolve, reject) => {
      if (!fs.existsSync(modelPath)) {
        LogHelper.title('Model Loader')

        reject(
          new Error(
            'The global resolvers NLP model does not exist, please run: npm run train'
          )
        )
      } else {
        try {
          const container = await containerBootstrap()

          container.use(Nlp)
          container.use(LangAll)

          this.globalResolversNLPContainer = container.get('nlp')
          const nluManager = container.get('nlu-manager')
          // The spell checker will try to correct the words with the most probable distance, but it is not perfect
          nluManager.settings.spellCheck = false

          await this.globalResolversNLPContainer.load(modelPath)
          LogHelper.title('Model Loader')
          LogHelper.success('Global resolvers NLP model loaded')

          resolve()
        } catch (e) {
          reject(
            new Error(
              `An error occurred while loading the global resolvers NLP model. Details: ${e}`
            )
          )
        }
      }
    })
  }

  /**
   * Load the skills resolvers NLP model from the latest training
   */
  private loadSkillsResolversModel(modelPath: string): Promise<void> {
    return new Promise(async (resolve, reject) => {
      if (!fs.existsSync(modelPath)) {
        LogHelper.title('Model Loader')

        reject({
          type: 'warning',
          obj: new Error(
            'The skills resolvers NLP model does not exist, please run: npm run train'
          )
        })
      } else {
        try {
          const container = await containerBootstrap()

          container.use(Nlp)
          container.use(LangAll)

          this.skillsResolversNLPContainer = container.get('nlp')
          const nluManager = container.get('nlu-manager')
          // The spell checker will try to correct the words with the most probable distance, but it is not perfect
          nluManager.settings.spellCheck = false

          await this.skillsResolversNLPContainer.load(modelPath)
          LogHelper.success('Skills resolvers NLP model loaded')

          resolve()
        } catch (e) {
          reject(
            new Error(
              `An error occurred while loading the skills resolvers NLP model. Details: ${e}`
            )
          )
        }
      }
    })
  }

  /**
   * Load the main NLP model from the latest training
   */
  private loadMainModel(modelPath: string): Promise<void> {
    return new Promise(async (resolve, reject) => {
      if (!fs.existsSync(modelPath)) {
        LogHelper.title('Model Loader')

        reject({
          type: 'warning',
          obj: new Error(
            'The main NLP model does not exist, please run: npm run train'
          )
        })
      } else {
        try {
          const container = await containerBootstrap()

          container.register(
            'extract-builtin-??',
            new BuiltinMicrosoft({
              builtins: MICROSOFT_BUILT_IN_ENTITIES
            }),
            true
          )
          container.use(Nlp)
          container.use(LangAll)

          this.mainNLPContainer = container.get('nlp')
          const nluManager = container.get('nlu-manager')
          // The spell checker will try to correct the words with the most probable distance, but it is not perfect
          nluManager.settings.spellCheck = false

          await this.mainNLPContainer.load(modelPath)
          LogHelper.success('Main NLP model loaded')

          resolve()
        } catch (e) {
          reject(
            new Error(
              `An error occurred while loading the main NLP model. Details: ${e}`
            )
          )
        }
      }
    })
  }
}
