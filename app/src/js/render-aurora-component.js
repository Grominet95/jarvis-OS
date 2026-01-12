import { createElement } from 'react'
import * as auroraComponents from '@leon-ai/aurora'

import * as customAuroraComponents from '../custom-aurora-components'

export default function renderAuroraComponent(
  socket,
  component,
  supportedEvents
) {
  if (component) {
    let reactComponent = auroraComponents[component.component]
    /**
     * Find custom component if a former component is not found
     */
    if (!reactComponent) {
      reactComponent = customAuroraComponents[component.component]
    }

    if (!reactComponent) {
      console.error(`Component ${component} not found`)
    }

    // Check if the browsed component has a supported event and bind it
    if (reactComponent) {
      component.events.forEach((event) => {
        if (supportedEvents.includes(event.type)) {
          component.props[event.type] = (data) => {
            const { method } = event

            socket.emit('widget-event', { method, data })
          }
        }
      })
    }

    // When children is a component, then wrap it in an array to render properly
    const isComponent = !!component.props?.children?.component
    if (isComponent) {
      component.props.children = [component.props.children]
    }

    if (component.props?.children && Array.isArray(component.props.children)) {
      component.props.children = component.props.children.map((child) => {
        return renderAuroraComponent(socket, child, supportedEvents)
      })
    }

    return createElement(reactComponent, component.props)
  }
}
