export type SupportedWidgetEvent = (typeof SUPPORTED_WIDGET_EVENTS)[number]
interface WidgetEvent {
  type: SupportedWidgetEvent
  id: string
}

export const SUPPORTED_WIDGET_EVENTS = [
  'onClick',
  'onSubmit',
  'onChange',
  'onStart',
  'onEnd'
] as const

function generateId(): string {
  return Math.random().toString(36).substring(2, 7)
}

export abstract class WidgetComponent<T = unknown> {
  public readonly component: string
  public readonly id: string
  public readonly props: T
  public readonly events: WidgetEvent[]

  protected constructor(props: T) {
    this.component = this.constructor.name
    this.id = `${this.component.toLowerCase()}-${generateId()}`
    this.props = props
    this.events = this.parseEvents()
  }

  private parseEvents(): WidgetEvent[] {
    if (!this.props) {
      return []
    }

    const eventTypes = Object.keys(this.props).filter(
      (key) =>
        key.startsWith('on') &&
        SUPPORTED_WIDGET_EVENTS.includes(key as SupportedWidgetEvent)
    ) as SupportedWidgetEvent[]

    return eventTypes.map((type) => ({
      type,
      id: `${this.id}_${type.toLowerCase()}-${generateId()}`,
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-expect-error
      method: this.props[type]()
    }))
  }
}
