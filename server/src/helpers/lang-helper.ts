import type { LongLanguageCode, ShortLanguageCode } from '@/types'
import { LANG_CONFIGS } from '@/constants'

export class LangHelper {
  /**
   * Get short language codes
   * @example getShortCodes() // ["en", "fr"]
   */
  public static getShortCodes(): ShortLanguageCode[] {
    const longLanguages = Object.keys(LANG_CONFIGS) as LongLanguageCode[]

    return longLanguages.map((lang) => LANG_CONFIGS[lang].short)
  }

  /**
   * Get long language code of the given short language code
   * @param shortCode The short language code of the language
   * @example getLongCode('en') // en-US
   */
  public static getLongCode(shortCode: ShortLanguageCode): LongLanguageCode {
    for (const longLanguage in LANG_CONFIGS) {
      const longLanguageType = longLanguage as LongLanguageCode
      const lang = LANG_CONFIGS[longLanguageType]

      if (lang.short === shortCode) {
        return longLanguageType
      }
    }

    return 'en-US'
  }

  /**
   * Get short language code of the given long language code
   * @param longCode The long language code of the language
   * @example getShortCode('en-US') // en
   */
  public static getShortCode(longCode: LongLanguageCode): ShortLanguageCode {
    return LANG_CONFIGS[longCode].short
  }

  /**
   * Get action loop stop words of the given long language code
   * @param shortCode The short language code of the language
   * @example getActionLoopStopWords('en-US') // ["stop", "break", "exit"]
   */
  public static getActionLoopStopWords(shortCode: ShortLanguageCode): string[] {
    return LANG_CONFIGS[LangHelper.getLongCode(shortCode)]
      .action_loop_stop_words
  }
}
