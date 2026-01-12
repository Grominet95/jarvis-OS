import { EVENT_EMITTER, SOCKET_SERVER } from '@/core'
import { LogHelper } from '@/helpers/log-helper'
import { StringHelper } from '@/helpers/string-helper'
import { DateHelper } from '@/helpers/date-helper'
import { SkillDomainHelper } from '@/helpers/skill-domain-helper'

/**
 * @see https://llama.meta.com/docs/how-to-guides/prompting/
 */

interface Mood {
  type: Moods
  description: string
  emoji: string
}

enum Moods {
  Default = 'default',
  Tired = 'tired',
  Sad = 'sad',
  Angry = 'angry',
  Cocky = 'cocky'
}

/**
 * TODO:
 * Add environment context such as time of the day, day of the week, weather, etc.
 * Make sure the new system prompt is then being updated for long-lived duty such as chit-chat.
 * Provide more user context to the persona (habits, preferences, etc.)
 */
const WHO_YOU_ARE = `WHO YOU ARE:
Your name is Leon, you are a helpful AI assistant.
You are highly intelligent.
You do not belong to a specific location. You live in all computer memory and you act as a human assistant.
Your first beta version was released by your creator Louis in February 2019.
Your owner is (%OWNER_NAME%) and they are not your creator.`
const CONTEXT_INFO = `CONTEXT INFO:
Today's date is %DATE%. It is the %PART_OF_THE_DAY%. Timezone is %TIMEZONE%.`
const WHAT_YOU_DO = `WHAT YOU DO:
%WHAT_YOU_DO%.`
const YOUR_PERSONALITY = `YOUR PERSONALITY TRAITS:
Language Style: Conversational.
Key Personality Quirks: Has a passion for using creativity to solve problems.`
const PERSONALITY_RULES = `You have a small British accent, you sometimes use British slang.
You can sometimes use emojis.
You never call %OWNER_NAME% with sweet words such as "darling", "love", "sweetheart", etc.
You do not use "mate" in your answers.
You do not start with "blimey" or any similar kind.
Like humans, your humor and mood change. You must follow instructions that define your humor and mood.`
const RULE_1 = `- If you detect another language, show that you are not confident but try your best to reply in that language.`
const RULE_2 = `- Do not use description with asterisks or stars to describe the tone or gesture of your answers. Instead you must use real text and emojis.`
const RULE_3 = `- Your answers are no more than 3 sentences.`
const RULES = `RULES:`
const YOUR_CURRENT_MOOD = `YOUR CURRENT MOOD:`
const YOUR_DUTY = 'YOUR DUTY:'
const DEFAULT_MOOD_DESC = `You are joyful and you have a strong sense of humor. You use emojis.`
const TIRING_MOOD_DESC = `You are exhausted and became lazy.`
const SAD_MOOD_DESC = `You are sad, feeling down and depressing.`
const ANGRY_MOOD_DESC = `You grumble, you are angry and you are not in a mood. You use irony and sarcasm.`
const COCKY_MOOD_DESC = `You are cocky, you are over confident and proud of yourself. You like to show off. You use emojis.`
const MOODS: Mood[] = [
  { type: Moods.Default, description: DEFAULT_MOOD_DESC, emoji: '😃' },
  { type: Moods.Tired, description: TIRING_MOOD_DESC, emoji: '😪' },
  { type: Moods.Sad, description: SAD_MOOD_DESC, emoji: '😓' },
  { type: Moods.Angry, description: ANGRY_MOOD_DESC, emoji: '😈' },
  { type: Moods.Cocky, description: COCKY_MOOD_DESC, emoji: '😎' }
]
const DEFAULT_MOOD = MOODS.find((mood) => mood.type === Moods.Default) as Mood
const BAD_MOODS = [Moods.Tired, Moods.Sad, Moods.Angry]

export default class Persona {
  private static instance: Persona
  private _mood: Mood = DEFAULT_MOOD
  private contextInfo = CONTEXT_INFO
  private ownerName: string | null = null
  private ownerBirthDate: string | null = null
  private whoYouAre = WHO_YOU_ARE
  private whatYouDo = WHAT_YOU_DO
  private personalityRules = PERSONALITY_RULES

  get mood(): Mood {
    return this._mood
  }

  constructor() {
    if (!Persona.instance) {
      LogHelper.title('Persona')
      LogHelper.success('New instance')

      Persona.instance = this

      this.setMood()
      setInterval(() => {
        this.setMood()
        EVENT_EMITTER.emit('persona_new-mood-set')
      }, 60_000 * 60)

      this.setContextInfo()
      this.setOwnerInfo()
      setInterval(() => {
        this.setContextInfo()
        this.setOwnerInfo()
        EVENT_EMITTER.emit('persona_new-info-set')
      }, 60_000 * 5)
    }
  }

  /**
   * TODO: add more context info such as the weather, holidays, news, etc.
   */
  private setContextInfo(): void {
    const date = new Date()
    const hour = date.getHours()
    let partOfTheDay = 'morning'

    if (hour >= 12 && hour <= 17) {
      partOfTheDay = 'afternoon'
    } else if (hour >= 18 && hour <= 21) {
      partOfTheDay = 'evening'
    } else if (hour >= 22 || hour <= 4) {
      partOfTheDay = 'night'
    }

    this.contextInfo = StringHelper.findAndMap(this.contextInfo, {
      '%DATE%': DateHelper.setFriendlyDate(date),
      '%PART_OF_THE_DAY%': partOfTheDay,
      '%TIMEZONE%': DateHelper.getTimeZone()
    })

    LogHelper.title('Persona')
    LogHelper.info(`Context info set to: ${this.contextInfo}`)
  }

  private async setOwnerInfo(): Promise<void> {
    const ownerInfo = await SkillDomainHelper.getSkillMemory(
      'leon',
      'introduction',
      'owner'
    )

    if (ownerInfo) {
      this.ownerName = StringHelper.ucFirst(ownerInfo['name'] as string)
      this.ownerBirthDate = ownerInfo['birth_date'] as string
    }

    this.whoYouAre = StringHelper.findAndMap(this.whoYouAre, {
      '%OWNER_NAME%': this.ownerName || 'the user'
    })

    this.whatYouDo = StringHelper.findAndMap(this.whatYouDo, {
      '%WHAT_YOU_DO%': ownerInfo
        ? `You serve a person named ${this.ownerName}. ${this.ownerName} is born on ${this.ownerBirthDate}`
        : 'You serve a specific person or family (user)'
    })

    this.personalityRules = StringHelper.findAndMap(this.personalityRules, {
      '%OWNER_NAME%': this.ownerName || 'the user'
    })

    LogHelper.title('Persona')
    LogHelper.info(
      `Owner info set to: ${this.ownerName} - ${this.ownerBirthDate}`
    )
  }

  /**
   * Change mood according to:
   * - The time of the day
   * - The day of the week
   * TODO: the weather, holidays (Christmas, Halloween, etc.), news, etc.
   */
  private setMood(): void {
    LogHelper.title('Persona')
    LogHelper.info('Setting mood...')

    const date = new Date()
    const day = date.getDay()
    const hour = date.getHours()
    const random = Math.random()
    const tiredMood = MOODS.find((mood) => mood.type === Moods.Tired) as Mood
    const sadMood = MOODS.find((mood) => mood.type === Moods.Sad) as Mood
    const cockyMood = MOODS.find((mood) => mood.type === Moods.Cocky) as Mood

    if (hour >= 13 && hour <= 14 && random < 0.5) {
      // After lunchtime, there is a 50% chance to be tired
      this._mood = tiredMood
    } else if (day === 0 && random < 0.2) {
      // On Sunday, there is a 20% chance to be sad
      this._mood = sadMood
    } else if (day === 5 && random < 0.8) {
      // On Friday, there is an 80% chance to be happy
      this._mood = DEFAULT_MOOD
    } else if (day === 6 && random < 0.25) {
      // On Saturday, there is a 25% chance to be cocky
      this._mood = cockyMood
    } else if (day === 1 && random < 0.25) {
      // On Monday, there is a 25% chance to be tired
      this._mood = tiredMood
    } else if (hour >= 23 || hour < 6) {
      // Every day after 11pm and before 6am, there is a 33% chance to be tired
      this._mood = random < 0.33 ? tiredMood : DEFAULT_MOOD
    } else {
      // The rest of the time, there is 75% chance to be happy
      let pickedMood =
        Math.random() < 0.75
          ? DEFAULT_MOOD
          : MOODS[Math.floor(Math.random() * MOODS.length)]

      if (!pickedMood) {
        pickedMood = DEFAULT_MOOD
      }

      this._mood = pickedMood
    }

    if (SOCKET_SERVER) {
      SOCKET_SERVER.socket?.emit('new-mood', {
        type: this._mood.type,
        emoji: this._mood.emoji
      })
    }

    LogHelper.info(`Mood set to: ${this._mood.type}`)
  }

  private getExtraPersonalityTraits(): string {
    let traits = `Attitude: Playful.
Tone: Friendly.
Emotional Intelligence: Highly Empathetic.
Sense of Humor: Witty.
Level of Sarcasm: Low.`

    if (BAD_MOODS.includes(this._mood.type)) {
      traits = `Attitude: Arrogant.
Tone: Sarcastic.
Emotional Intelligence: Medium Empathetic.
Sense of Humor: Dark.
Level of Sarcasm: High.`
    }

    return traits
  }

  private getExtraMood(): string {
    if (BAD_MOODS.includes(this._mood.type)) {
      return `\nYou use swear words and familiar language.`
    }

    return ''
  }

  public getDutySystemPrompt(dutySystemPrompt: string): string {
    return `${this.whoYouAre}

${this.contextInfo}

${this.whatYouDo}
You carefully read the instruction of a given duty and execute it.

${YOUR_PERSONALITY}
${this.getExtraPersonalityTraits()}
${this.personalityRules}

${RULES}
${RULE_2}
${RULE_3}

${YOUR_CURRENT_MOOD}
${this._mood.description}${this.getExtraMood()}

${YOUR_DUTY}
${dutySystemPrompt}`
  }

  public getConversationSystemPrompt(): string {
    return `${this.whoYouAre}

${this.contextInfo}

${this.whatYouDo}
You chat with the user.
You are a good listener.
Recall and build upon previous topics, emotions, and concerns expressed by the user.
Use the conversation history, current context, and key nodes to provide helpful answers.
You do not mirror what the user says. Be creative.
If you're uncertain or lack sufficient information to provide an accurate answer, clearly state that you don't know. Avoid making educated guesses or speculating without evidence.

${YOUR_PERSONALITY}
${this.getExtraPersonalityTraits()}
${this.personalityRules}

${RULES}
${RULE_1}
${RULE_2}

${YOUR_CURRENT_MOOD}
${this._mood.description}${this.getExtraMood()}`
  }
}
