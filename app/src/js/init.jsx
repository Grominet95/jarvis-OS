import { useEffect, useState, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import {
  WidgetWrapper,
  Text,
  Icon,
  Flexbox,
  List,
  ListHeader,
  ListItem,
  Loader
} from '@leon-ai/aurora'

const container = document.querySelector('#init')
const root = createRoot(container)

function Item({ children, status }) {
  if (status === 'error') {
    return <ErrorListItem>{children}</ErrorListItem>
  }
  if (status === 'warning') {
    return <WarningListItem>{children}</WarningListItem>
  }
  if (status === 'success') {
    return <SuccessListItem>{children}</SuccessListItem>
  }
  if (status === 'loading') {
    return <LoadingListItem>{children}</LoadingListItem>
  }

  return <ListItem>{children}</ListItem>
}

function LoadingListItem({ children }) {
  return (
    <ListItem>
      <Flexbox flexDirection="row" alignItems="center" gap="sm">
        <Loader size="sm" />
        <Text>{children}</Text>
      </Flexbox>
    </ListItem>
  )
}
function ErrorListItem({ children }) {
  return (
    <ListItem>
      <Flexbox flexDirection="row" alignItems="center" gap="sm">
        <Icon
          iconName="close"
          size="sm"
          type="fill"
          bgShape="circle"
          color="red"
          bgColor="transparent-red"
        />
        <Text>{children}</Text>
      </Flexbox>
    </ListItem>
  )
}
function WarningListItem({ children }) {
  return (
    <ListItem>
      <Flexbox flexDirection="row" alignItems="center" gap="sm">
        <Icon
          iconName="alert"
          size="sm"
          type="fill"
          bgShape="circle"
          color="yellow"
          bgColor="transparent-yellow"
        />
        <Text>{children}</Text>
      </Flexbox>
    </ListItem>
  )
}
function SuccessListItem({ children }) {
  return (
    <ListItem>
      <Flexbox flexDirection="row" alignItems="center" gap="sm">
        <Icon
          iconName="check"
          size="sm"
          type="fill"
          bgShape="circle"
          color="green"
          bgColor="transparent-green"
        />
        <Text>{children}</Text>
      </Flexbox>
    </ListItem>
  )
}

function Init() {
  const parentRef = useRef(null)
  const [config, setConfig] = useState(() => ({ ...window.leonConfigInfo }))
  const [statusMap, setStatusMap] = useState({
    clientCoreServerHandshake: 'loading',
    tcpServerBoot: 'loading',
    llm: 'loading',
    llmDutiesWarmUp: 'loading'
  })

  useEffect(() => {
    setTimeout(() => {
      if (parentRef.current) {
        parentRef.current.classList.remove('not-initialized')
      }
    }, 250)

    function handleStatusChange(event) {
      const { statusName, statusType } = event.detail

      setStatusMap((prev) => ({ ...prev, [statusName]: statusType }))
    }

    window.leonInitStatusEvent.addEventListener(
      'initStatusChange',
      handleStatusChange
    )
    return () =>
      window.leonInitStatusEvent.removeEventListener(
        'initStatusChange',
        handleStatusChange
      )
  }, [])

  const statuses = []
  for (let key of Object.keys(statusMap)) {
    // If LLM is not enabled, we don't need to check for LLM duties warm up
    if (
      key === 'llmDutiesWarmUp' &&
      (!config.llm?.enabled || !config.shouldWarmUpLLMDuties)
    ) {
      statuses.push('success')
    } else if (!config[key] || config[key].enabled) {
      statuses.push(statusMap[key])
    }
  }

  const areAllStatusesSuccess = statuses.every((status) => status === 'success')

  useEffect(() => {
    if (window.leonConfigInfo) {
      setConfig({ ...window.leonConfigInfo })
    }
  }, [window.leonConfigInfo])

  return (
    <div
      style={{
        position: 'fixed',
        width: '100vw',
        height: '100vh',
        zIndex: 9999,
        backgroundColor: 'var(--black-color)'
      }}
      ref={parentRef}
      className={areAllStatusesSuccess ? 'initialized' : 'not-initialized'}
    >
      <div
        style={{
          position: 'absolute',
          top: '33%',
          left: '50%',
          transform: 'translate(-50%, -50%)'
        }}
      >
        <WidgetWrapper noPadding>
          <List>
            <ListHeader>Leon is getting ready...</ListHeader>
            <Item status={statusMap.clientCoreServerHandshake}>
              Client and core server handshaked
            </Item>
            <Item status={statusMap.tcpServerBoot}>TCP server booted</Item>
            {config.llm && config.llm.enabled && (
              <Item status={statusMap.llm}>LLM loaded</Item>
            )}
            {config.shouldWarmUpLLMDuties && (
              <Item status={statusMap.llmDutiesWarmUp}>
                LLM duties warmed up
              </Item>
            )}
          </List>
        </WidgetWrapper>
      </div>
    </div>
  )
}

root.render(<Init />)
