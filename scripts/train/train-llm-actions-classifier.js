import path from 'node:path'
import fs from 'node:fs'

import { LLM_ACTIONS_CLASSIFIER_PATH } from '@/constants'
import { LogHelper } from '@/helpers/log-helper'
import { SkillDomainHelper } from '@/helpers/skill-domain-helper'

// TODO: need to handle multi languages
const LANG = 'en'

/**
 * Train LLM actions classifier
 */
export default () =>
  new Promise(async (resolve) => {
    LogHelper.title('LLM actions classifier training')

    const skillDomains = await SkillDomainHelper.getSkillDomains()
    let actionsArray = []

    for (const [, currentDomain] of skillDomains) {
      const skillKeys = Object.keys(currentDomain.skills)

      for (let i = 0; i < skillKeys.length; i += 1) {
        const { name: skillName } = currentDomain.skills[skillKeys[i]]
        const currentSkill = currentDomain.skills[skillKeys[i]]

        const configFilePath = path.join(
          currentSkill.path,
          'config',
          `${LANG}.json`
        )

        if (fs.existsSync(configFilePath)) {
          const { actions } = await SkillDomainHelper.getSkillConfig(
            configFilePath,
            LANG
          )
          const actionsKeys = Object.keys(actions)

          for (let j = 0; j < actionsKeys.length; j += 1) {
            const actionName = actionsKeys[j]
            const actionObj = actions[actionName]

            /**
             * Skip actions without utterance samples to make sure we only match
             * actions that are actionable from an utterance
             */
            if (!actionObj.utterance_samples) {
              continue
            }

            const actionObjWithUtteranceSamples = {
              name: `${currentDomain.domainId}.${skillName}.${actionName}`,
              // Only grab the first utterance sample when utterance_samples exists
              sample: actionObj.utterance_samples
                ? actionObj.utterance_samples[0]
                : ''
            }

            actionsArray.push(actionObjWithUtteranceSamples)
          }
        }
      }
    }

    const jsonObject = {
      intents: actionsArray
    }

    await fs.promises.writeFile(
      LLM_ACTIONS_CLASSIFIER_PATH,
      JSON.stringify(jsonObject, null, 0)
    )

    resolve()
  })
