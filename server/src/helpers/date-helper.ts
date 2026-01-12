import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc.js'
import timezone from 'dayjs/plugin/timezone.js'

import { TIME_ZONE } from '@/constants'
import { LogHelper } from '@/helpers/log-helper'

dayjs.extend(utc)
dayjs.extend(timezone)

export class DateHelper {
  /**
   * Get date time
   * @example getDateTime() // 2022-09-12T12:42:57+08:00
   */
  public static getDateTime(): string {
    return dayjs().tz(this.getTimeZone()).format()
  }

  /**
   * Get friendly date
   * @example setFriendlyDate() // Thursday, May 23, 2024
   */
  public static setFriendlyDate(date: Date): string {
    return dayjs(date).tz(this.getTimeZone()).format('dddd, MMMM D, YYYY')
  }

  /**
   * Get time zone
   * @example getTimeZone() // Asia/Shanghai
   */
  public static getTimeZone(): string {
    let { timeZone } = Intl.DateTimeFormat().resolvedOptions()

    if (TIME_ZONE) {
      // Verify if the time zone is valid
      try {
        Intl.DateTimeFormat(undefined, { timeZone: TIME_ZONE })
        timeZone = TIME_ZONE
      } catch (e) {
        LogHelper.warning(
          `The time zone "${TIME_ZONE}" is not valid. Falling back to "${timeZone}". Details: ${e}`
        )
      }
    }

    return timeZone
  }
}
