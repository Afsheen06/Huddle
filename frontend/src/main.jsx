import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { AllCommunityModule, colorSchemeDarkBlue, themeQuartz } from 'ag-grid-community'
import { AgGridProvider, AgGridReact } from 'ag-grid-react'
import './styles.css'

const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const communityModules = [AllCommunityModule]
const huddleGridTheme = themeQuartz.withPart(colorSchemeDarkBlue).withParams({
  backgroundColor: '#10171e',
  foregroundColor: '#e9eff4',
  accentColor: '#d8ff38',
  borderColor: '#27333d',
  headerBackgroundColor: '#141d25',
  headerTextColor: '#9baab5',
  oddRowBackgroundColor: '#131c24',
  rowHoverColor: '#202c35',
  selectedRowBackgroundColor: 'rgba(216, 255, 56, 0.12)',
  dataFontSize: 13,
  cellFontFamily: 'Inter, sans-serif',
  headerFontFamily: 'Inter, sans-serif',
  spacing: 7,
})

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || body.message || `Request failed (${response.status})`)
  return body
}

function amountParts(value, fallbackCurrency = 'USD') {
  if (value && typeof value === 'object') {
    return { value: Number(value.value || 0), currency: value.currency_code || fallbackCurrency }
  }
  return { value: Number(value || 0), currency: fallbackCurrency }
}

function money(value, currency = 'USD') {
  const amount = amountParts(value, currency)
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: amount.currency, maximumFractionDigits: 2 }).format(amount.value)
  } catch {
    return `${amount.value.toFixed(2)} ${amount.currency}`
  }
}

function amountTotal(entries, getAmount) {
  const totals = {}
  for (const entry of entries) {
    const amount = amountParts(getAmount(entry))
    totals[amount.currency] = (totals[amount.currency] || 0) + amount.value
  }
  const currencies = Object.keys(totals)
  if (!currencies.length) return '$0'
  if (currencies.length === 1) return money({ value: totals[currencies[0]], currency_code: currencies[0] })
  return `${currencies.length} currencies`
}

function dateLabel(value) {
  if (!value) return '—'
  const date = new Date(`${value.slice(0, 10)}T00:00:00`)
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

function isBeforeToday(value) {
  if (!value) return false
  const dueDate = new Date(`${String(value).slice(0, 10)}T00:00:00`)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return !Number.isNaN(dueDate.valueOf()) && dueDate < today
}

function statusLabel(status) {
  return ({ not_billed: 'NOT BILLED', draft: 'DRAFT', sent_unpaid: 'DUE', overdue: 'OVERDUE', paid: 'PAID' })[status] || String(status || 'unknown').replaceAll('_', ' ').toUpperCase()
}

function StatusBadge({ value }) {
  const normalized = String(value || '').toLowerCase()
  const mapped = ({ sent: 'sent_unpaid', unpaid: 'sent_unpaid', partially_paid: 'sent_unpaid', paid_external: 'paid', marked_as_paid: 'paid', cancelled: 'not_billed' })[normalized] || normalized
  return <span className={`status-badge status-${mapped}`}>{statusLabel(mapped)}</span>
}

function Skeleton({ className = '' }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />
}

function Stat({ label, value, foot, tone = '' }) {
  return <div className={`stat ${tone}`}>
    <span className="stat-label">{label}</span>
    <strong className="display-number">{value}</strong>
    <span className="stat-foot">{foot}</span>
  </div>
}

function App() {
  const [summary, setSummary] = useState(null)
  const [board, setBoard] = useState([])
  const [roster, setRoster] = useState([])
  const [invoices, setInvoices] = useState([])
  const [queue, setQueue] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [selectedPlayer, setSelectedPlayer] = useState(null)
  const [quickFilter, setQuickFilter] = useState('')
  const [chatInput, setChatInput] = useState('')
  const [chatHistory, setChatHistory] = useState([])
  const [chatMessages, setChatMessages] = useState([])
  const [chatBusy, setChatBusy] = useState(false)
  const [latestActions, setLatestActions] = useState([])
  const [modalOpen, setModalOpen] = useState(false)
  const [rosterText, setRosterText] = useState('')
  const [parsedPlayers, setParsedPlayers] = useState(null)
  const [parseWarnings, setParseWarnings] = useState([])
  const [parseBusy, setParseBusy] = useState(false)
  const [savingRoster, setSavingRoster] = useState(false)
  const [busyQueueId, setBusyQueueId] = useState('')
  const [lastApproved, setLastApproved] = useState('')
  const chatEndRef = useRef(null)

  const refreshData = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true)
    else setLoading(true)
    try {
      const [nextSummary, nextBoard, nextInvoices, nextQueue, nextRoster] = await Promise.all([
        api('/summary'), api('/board'), api('/invoices'), api('/queue'), api('/roster'),
      ])
      setSummary(nextSummary)
      setBoard(nextBoard.players || [])
      setInvoices(nextInvoices.items || [])
      setQueue(nextQueue.items || [])
      setRoster(nextRoster.players || [])
      setError('')
    } catch (err) {
      setError(err.message || 'Could not reach Huddle. Is the backend running?')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { refreshData() }, [refreshData])
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [chatMessages, chatBusy])
  useEffect(() => {
    if (!notice) return undefined
    const timer = window.setTimeout(() => setNotice(''), 4200)
    return () => window.clearTimeout(timer)
  }, [notice])

  const invoicesByPlayer = useMemo(() => {
    const emailToPlayer = new Map(board.filter((player) => player.parent_email).map((player) => [player.parent_email.toLowerCase(), player]))
    return invoices.map((invoice) => {
      const recipient = invoice.primary_recipients?.[0]?.billing_info || {}
      const name = recipient.name?.full_name || recipient.name?.given_name || 'Unknown customer'
      const email = recipient.email_address || ''
      const detail = invoice.detail || {}
      const due = detail.payment_term?.due_date || invoice.due_date || ''
      const value = invoice.due_amount || invoice.amount || {}
      const linked = emailToPlayer.get(email.toLowerCase())
      const number = detail.invoice_number || invoice.id || '—'
      return {
        ...invoice,
        invoice_number: number,
        client: name,
        client_email: email,
        due_date: due,
        amount_value: amountParts(value).value,
        amount_currency: amountParts(value).currency,
        amount_display: money(value),
        roster_player: linked?.player_name || '',
        roster_key: linked?.player_name || '',
      }
    })
  }, [invoices, board])

  const filteredInvoices = useMemo(() => {
    if (!selectedPlayer) return invoicesByPlayer
    return invoicesByPlayer.filter((invoice) => invoice.roster_key === selectedPlayer || board.find((p) => p.player_name === selectedPlayer)?.invoice_id === invoice.id)
  }, [invoicesByPlayer, selectedPlayer, board])

  const collectedInvoices = invoices.filter((invoice) => ['PAID', 'PAID_EXTERNAL', 'MARKED_AS_PAID', 'PARTIALLY_PAID'].includes(String(invoice.status || '').toUpperCase()))
  const overdueInvoices = invoices.filter((invoice) =>
    ['SENT', 'UNPAID', 'PARTIALLY_PAID', 'PAYMENT_PENDING', 'SHARED'].includes(String(invoice.status || '').toUpperCase())
    && isBeforeToday(invoice.detail?.payment_term?.due_date || invoice.due_date),
  )
  const outstandingLabel = summary?.outstanding_by_currency
    ? (Object.keys(summary.outstanding_by_currency).length === 1
      ? money({ value: Object.values(summary.outstanding_by_currency)[0], currency_code: Object.keys(summary.outstanding_by_currency)[0] })
      : `${Object.keys(summary.outstanding_by_currency).length} currencies`)
    : '$0'
  const overdueLabel = amountTotal(overdueInvoices, (invoice) => invoice.due_amount || invoice.effective_due_amount || invoice.amount)
  const playersPaid = board.filter((player) => player.status === 'paid').length
  const paidPercent = board.length ? Math.round((playersPaid / board.length) * 100) : 0
  const pendingQueueItems = queue.filter((item) => item.status === 'pending')
  const failedQueueItems = queue.filter((item) => item.status === 'failed')
  const visibleQueueItems = [...pendingQueueItems, ...failedQueueItems]
  const collectedLabel = amountTotal(collectedInvoices, (invoice) => {
    const total = amountParts(invoice.amount)
    if (String(invoice.status || '').toUpperCase() === 'PARTIALLY_PAID') {
      const remaining = amountParts(invoice.due_amount || invoice.effective_due_amount || invoice.amount)
      return { value: Math.max(0, total.value - remaining.value), currency_code: total.currency }
    }
    return invoice.amount
  })

  const columnDefs = useMemo(() => [
    { field: 'invoice_number', headerName: 'INVOICE', minWidth: 115, flex: 0.75 },
    { field: 'client', headerName: 'CLIENT / PARENT', minWidth: 175, flex: 1.2 },
    { field: 'roster_player', headerName: 'PLAYER', minWidth: 135, flex: 0.9, valueFormatter: (params) => params.value || '—' },
    { field: 'status', headerName: 'STATUS', minWidth: 130, flex: 0.8, cellRenderer: StatusBadge },
    { field: 'due_date', headerName: 'DUE DATE', minWidth: 132, flex: 0.85, valueFormatter: (params) => dateLabel(params.value) },
    { field: 'amount_display', headerName: 'AMOUNT DUE', minWidth: 135, flex: 0.8, cellClass: 'amount-cell' },
  ], [])

  const defaultColDef = useMemo(() => ({ sortable: true, filter: true, resizable: true, suppressHeaderMenuButton: true }), [])

  async function sendChat(message = chatInput) {
    const content = message.trim()
    if (!content || chatBusy) return
    setChatInput('')
    setChatMessages((current) => [...current, { role: 'user', content }])
    setChatBusy(true)
    setError('')
    try {
      const result = await api('/chat', {
        method: 'POST',
        body: JSON.stringify({ message: content, history: chatHistory }),
      })
      setChatHistory(result.history || [...chatHistory, { role: 'user', content }, { role: 'assistant', content: result.reply }])
      setChatMessages((current) => [...current, { role: 'assistant', content: result.reply }])
      setLatestActions(result.actions || [])
      if (result.queue_items_created?.length) setNotice(`${result.queue_items_created.length} action${result.queue_items_created.length === 1 ? '' : 's'} added to the Referee queue for review.`)
      await refreshData(true)
    } catch (err) {
      setChatMessages((current) => [...current, { role: 'error', content: `I couldn't finish that request: ${err.message}` }])
      setLatestActions([])
    } finally {
      setChatBusy(false)
    }
  }

  async function handleParse() {
    if (!rosterText.trim()) return
    setParseBusy(true)
    setError('')
    try {
      const result = await api('/roster/parse', { method: 'POST', body: JSON.stringify({ raw_text: rosterText }) })
      setParsedPlayers((result.players || []).map((player) => ({ ...player })))
      setParseWarnings(result.warnings || [])
    } catch (err) {
      setError(`Roster parsing failed: ${err.message}`)
    } finally {
      setParseBusy(false)
    }
  }

  async function handleSaveRoster() {
    if (!parsedPlayers) return
    setSavingRoster(true)
    try {
      await api('/roster/save', { method: 'POST', body: JSON.stringify({ players: parsedPlayers }) })
      setModalOpen(false)
      setParsedPlayers(null)
      setRosterText('')
      setParseWarnings([])
      setNotice('Roster saved. The board has been refreshed.')
      await refreshData(true)
    } catch (err) {
      setError(`Could not save the roster: ${err.message}`)
    } finally {
      setSavingRoster(false)
    }
  }

  async function handleDemoSeed() {
    const accepted = window.confirm('Load the fictional 12-player demo roster? This replaces the roster currently saved on this computer. Demo parent emails will be blank, so no invoices can be created for them by mistake.')
    if (!accepted) return
    try {
      await api('/demo/seed', { method: 'POST' })
      setSelectedPlayer(null)
      setNotice('Demo roster loaded. Add real Sandbox buyer emails before billing.')
      await refreshData(true)
    } catch (err) {
      setError(`Could not load the demo roster: ${err.message}`)
    }
  }

  async function decideQueue(item, decision) {
    const actionVerb = item.action_type === 'cancel_invoice' ? 'cancel' : item.action_type === 'send_reminder' ? 'send a reminder for' : 'send'
    if (decision === 'approve' && !window.confirm(`Approve this action? Huddle will ${actionVerb} the listed invoice(s) through PayPal.`)) return
    setBusyQueueId(item.id)
    try {
      const result = await api(`/queue/${encodeURIComponent(item.id)}/${decision}`, {
        method: 'POST',
        ...(decision === 'reject' ? { body: JSON.stringify({}) } : {}),
      })
      if (decision === 'approve' && result.status === 'failed') {
        await refreshData(true)
        throw new Error(result.error || 'PayPal could not complete the approved action.')
      }
      if (decision === 'approve') {
        setLastApproved(item.id)
        window.setTimeout(() => setLastApproved(''), 1200)
      }
      setNotice(decision === 'approve' ? 'Approved action completed.' : 'Proposal rejected. No PayPal action was taken.')
      await refreshData(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyQueueId('')
    }
  }

  async function approveAll() {
    const pending = queue.filter((item) => item.status === 'pending')
    if (!pending.length) return
    if (!window.confirm(`Approve all ${pending.length} pending actions? This may send invoices or reminders, or cancel invoices in PayPal.`)) return
    setBusyQueueId('all')
    try {
      const result = await api('/queue/approve-all', { method: 'POST' })
      setNotice(`${result.approved_count || 0} queued action${result.approved_count === 1 ? '' : 's'} completed.`)
      await refreshData(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyQueueId('')
    }
  }

  function updateParsed(index, field, value) {
    setParsedPlayers((players) => players.map((player, i) => i === index ? {
      ...player,
      [field]: field === 'amount' ? (value === '' ? null : Number(value)) : value,
      missing_fields: field === 'parent_email'
        ? (value.trim() ? (player.missing_fields || []).filter((entry) => entry !== 'parent_email') : [...new Set([...(player.missing_fields || []), 'parent_email'])])
        : player.missing_fields,
    } : player))
  }

  return <AgGridProvider modules={communityModules}>
    <div className="app-shell">
      <div className="field-lines" aria-hidden="true" />
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Huddle home">
          <span className="brand-mark">H</span>
          <span className="brand-name">HUDDLE<span className="brand-period">.</span></span>
        </a>
        <div className="brand-copy"><span>Your club's AI treasurer</span><span className="sandbox-badge"><i /> PayPal Sandbox</span></div>
        <div className="header-actions">
          <span className="live-indicator"><i /> {refreshing ? 'UPDATING' : 'LIVE BOARD'}</span>
          <button className="button button-quiet import-button" onClick={() => setModalOpen(true)}><span>＋</span> Import roster</button>
        </div>
      </header>

      <main id="top" className="page-content">
        {error && <div className="alert alert-error" role="alert"><span>!</span><div><strong>Something needs attention</strong><p>{error}</p></div><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
        {notice && <div className="toast" role="status">✓ &nbsp;{notice}</div>}

        <section className="scoreboard section-block" aria-labelledby="scoreboard-title">
          <div className="section-heading scoreboard-heading">
            <div><span className="eyebrow">MATCH DAY // FINANCE</span><h1 id="scoreboard-title">CLUB <span>SCOREBOARD</span></h1></div>
            <div className="board-meta"><span>{board.length ? `${board.length} PLAYERS ON ROSTER` : 'NO ROSTER LOADED'}</span><button className="text-button" onClick={handleDemoSeed}>Load demo roster <span>↗</span></button></div>
          </div>
          <div className="score-grid">
            {loading ? <><Skeleton className="stat-skeleton" /><Skeleton className="stat-skeleton" /><Skeleton className="stat-skeleton" /><Skeleton className="stat-skeleton" /></> : <>
              <Stat label="COLLECTED" value={collectedLabel} foot={`${summary?.paid_invoices || 0} paid invoice${summary?.paid_invoices === 1 ? '' : 's'}`} tone="stat-paid" />
              <Stat label="OUTSTANDING" value={outstandingLabel} foot={`${summary?.unpaid_invoices || 0} sent & unpaid`} />
              <Stat label="OVERDUE" value={overdueLabel} foot={`${summary?.overdue_invoices || 0} invoice${summary?.overdue_invoices === 1 ? '' : 's'} past due`} tone="stat-overdue" />
              <div className="stat stat-progress"><span className="stat-label">PLAYERS PAID</span><strong className="display-number">{playersPaid}<small>/{board.length}</small></strong><div className="progress-track"><span style={{ width: `${paidPercent}%` }} /></div><span className="stat-foot">{paidPercent}% of roster settled</span></div>
            </>}
          </div>
          <div className="scoreboard-rule"><span>SEASON CONTROL</span><span>USD · SANDBOX ENVIRONMENT</span></div>
        </section>

        <section className="section-block roster-section" aria-labelledby="roster-title">
          <div className="section-heading">
            <div><span className="eyebrow">THE SQUAD</span><h2 id="roster-title">ROSTER <span>BOARD</span></h2></div>
            <div className="roster-legend"><span><i className="legend-dot dot-paid" /> Paid</span><span><i className="legend-dot dot-due" /> Due</span><span><i className="legend-dot dot-late" /> Overdue</span><span><i className="legend-dot dot-draft" /> Draft</span></div>
          </div>
          {loading ? <div className="roster-grid">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="player-skeleton" />)}</div> : board.length ? <div className="roster-grid">
            {board.map((player, index) => <button key={`${player.player_name}-${index}`} className={`player-tile tile-${player.status} ${selectedPlayer === player.player_name ? 'tile-selected' : ''}`} onClick={() => setSelectedPlayer((current) => current === player.player_name ? null : player.player_name)} title={selectedPlayer === player.player_name ? 'Clear player filter' : `Filter ledger to ${player.player_name}`}>
              <div className="tile-top"><span className="jersey-number">{player.jersey_number || String(index + 1).padStart(2, '0')}</span><span className={`tile-status status-${player.status}`}>{player.status === 'overdue' ? `${player.days_overdue}D LATE` : statusLabel(player.status)}</span></div>
              <strong className="player-name">{player.player_name}</strong>
              <span className="player-fee">{money(player.amount || player.roster_amount || 0)} <small>{player.group || 'CLUB PLAYER'}</small></span>
            </button>)}
          </div> : <EmptyState title="No players on the roster" text="Import a roster or load the demo team to fill the board." />}
          {selectedPlayer && <div className="filter-note">LEDGER FILTERED TO <strong>{selectedPlayer}</strong><button onClick={() => setSelectedPlayer(null)}>Clear filter ×</button></div>}
        </section>

        <div className="main-columns">
          <section className="panel ledger-panel" aria-labelledby="ledger-title">
            <div className="panel-heading">
              <div><span className="eyebrow">PAYPAL SANDBOX</span><h2 id="ledger-title">THE <span>LEDGER</span></h2></div>
              <span className="record-count">{filteredInvoices.length} RECORDS</span>
            </div>
            <div className="ledger-toolbar"><label className="search-box"><span>⌕</span><input aria-label="Search invoices" value={quickFilter} onChange={(event) => setQuickFilter(event.target.value)} placeholder="Search name, email, status…" /></label><button className="button button-quiet refresh-button" onClick={() => refreshData(true)} disabled={refreshing}>{refreshing ? 'Updating…' : '↻ Refresh'}</button></div>
            <div className="grid-frame">
              {loading ? <div className="grid-loading"><Skeleton /><Skeleton /><Skeleton /><Skeleton /></div> : <AgGridReact
                theme={huddleGridTheme}
                rowData={filteredInvoices}
                columnDefs={columnDefs}
                defaultColDef={defaultColDef}
                quickFilterText={quickFilter}
                animateRows
                rowHeight={54}
                headerHeight={44}
                domLayout="autoHeight"
                overlayNoRowsTemplate={'<span class="grid-empty">No invoices yet. Ask Huddle to prepare one.</span>'}
              />}
            </div>
          </section>

          <section className="panel referee-panel" aria-labelledby="referee-title">
            <div className="panel-heading referee-heading">
              <div><span className="eyebrow">HUMAN-IN-THE-LOOP SAFETY</span><h2>THE <span>REFEREE</span></h2></div>
              <span className="queue-count">{pendingQueueItems.length} WAITING</span>
            </div>
            <p className="panel-intro">Nothing reaches a parent until you say so. Review every action before it leaves the bench.</p>
            {pendingQueueItems.length > 0 && <button className="button approve-all" onClick={approveAll} disabled={busyQueueId === 'all'}>{busyQueueId === 'all' ? 'Approving…' : `Approve all ${pendingQueueItems.length} pending`}</button>}
            <div className="queue-list">
              {loading ? <><Skeleton className="queue-skeleton" /><Skeleton className="queue-skeleton" /></> : visibleQueueItems.length ? visibleQueueItems.map((item) => <article className={`queue-card ${item.status === 'failed' ? 'queue-failed' : lastApproved === item.id ? 'queue-approved' : ''}`} key={item.id}>
                <div className="queue-card-head"><span className="queue-action">{String(item.action_type).replaceAll('_', ' ')}</span><span className={item.status === 'failed' ? 'queue-failed-label' : 'queue-target-count'}>{item.status === 'failed' ? 'FAILED' : `${item.target_invoice_ids?.length || 0} INVOICE${item.target_invoice_ids?.length === 1 ? '' : 'S'}`}</span></div>
                <p>{item.summary}</p>
                {item.reminder_message && <blockquote>{item.reminder_message}</blockquote>}
                <div className="queue-targets">{(item.targets || []).map((target) => <span key={target.id}>{target.recipient_name || target.recipient_email || target.id} · {target.invoice_number || target.id}</span>)}</div>
                {item.status === 'failed' ? <p className="queue-failure-detail" role="alert">PayPal could not complete this action: {item.error || 'Please check the invoice in PayPal Sandbox.'}</p> : <div className="queue-buttons"><button className="button button-approve" onClick={() => decideQueue(item, 'approve')} disabled={busyQueueId === item.id}>{busyQueueId === item.id ? 'Working…' : 'Approve'}</button><button className="button button-reject" onClick={() => decideQueue(item, 'reject')} disabled={busyQueueId === item.id}>Reject</button></div>}
              </article>) : <div className="queue-empty"><span className="whistle">◉</span><strong>The Referee has nothing waiting.</strong><p>Proposed sends and reminders will appear here for your review.</p></div>}
            </div>
          </section>
        </div>

        <div className="bottom-columns">
          <section className="panel chat-panel" aria-labelledby="chat-title">
            <div className="panel-heading">
              <div><span className="eyebrow">YOUR CLUB, ON CALL</span><h2>ASK THE <span>TREASURER</span></h2></div>
              <span className="chat-online"><i /> GEMINI READY</span>
            </div>
            <div className="chat-messages" aria-live="polite">
              {!chatMessages.length && <div className="chat-welcome"><span className="welcome-mark">H</span><div><strong>What does the club need?</strong><p>Ask for a summary, a draft invoice, or a reminder proposal.</p></div></div>}
              {chatMessages.map((message, index) => <div key={`${message.role}-${index}`} className={`chat-message message-${message.role}`}><span className="message-avatar">{message.role === 'user' ? 'YOU' : message.role === 'error' ? '!' : 'H'}</span><p>{message.content}</p></div>)}
              {chatBusy && <div className="chat-message message-assistant"><span className="message-avatar">H</span><div className="typing-indicator"><i /><i /><i /></div></div>}
              <div ref={chatEndRef} />
            </div>
            <div className="prompt-chips">
              {['Bill everyone $20 for November training, due in 10 days', "Who hasn't paid?", 'Chase the overdue ones', 'Send all the drafts'].map((prompt) => <button key={prompt} onClick={() => sendChat(prompt)} disabled={chatBusy}>{prompt}</button>)}
            </div>
            <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); sendChat() }}>
              <textarea aria-label="Message Huddle" value={chatInput} onChange={(event) => setChatInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendChat() } }} placeholder="Ask Huddle about your club…" rows={1} />
              <button className="send-button" type="submit" disabled={!chatInput.trim() || chatBusy} aria-label="Send message">↑</button>
            </form>
            <div className="composer-foot"><span>ENTER TO SEND · SHIFT + ENTER FOR NEW LINE</span><span>AI CAN MAKE MISTAKES. REVIEW ACTIONS.</span></div>
          </section>

          <section className="panel actions-panel" aria-labelledby="actions-title">
            <div className="panel-heading"><div><span className="eyebrow">TRANSPARENT BY DESIGN</span><h2>WHAT THE AGENT <span>DID</span></h2></div><span className="record-count">{latestActions.length} THIS TURN</span></div>
            {latestActions.length ? <div className="action-list">{latestActions.map((action, index) => <article className="agent-action" key={`${action.tool_name}-${index}`}>
              <div className="action-head"><span className="action-check">{action.error ? '!' : '✓'}</span><strong>{action.tool_name}</strong><span className={`action-state ${action.error ? 'state-error' : ''}`}>{action.error ? 'NEEDS ATTENTION' : 'COMPLETE'}</span></div>
              <div className="action-args"><span>ARGUMENTS</span><code>{JSON.stringify(action.arguments || {})}</code></div>
              <p className="action-result">{action.error || summarizeResult(action.result)}</p>
            </article>)}</div> : <div className="action-empty"><span className="action-symbol">⌁</span><strong>Your agent activity appears here.</strong><p>Tool calls are shown in plain sight, including what Huddle asked PayPal to do.</p></div>}
            <div className="safety-foot"><span className="safety-lock">◇</span><p><strong>Safety first.</strong> Drafts are created directly. Sends, reminders, and cancellations wait in the Referee queue for a human decision.</p></div>
          </section>
        </div>

        <footer className="page-footer"><span>HUDDLE · CLUB TREASURY, IN YOUR CORNER</span><span>DEMO MODE · PAYPAL SANDBOX</span></footer>
      </main>

      {modalOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setModalOpen(false) }}>
        <section className="roster-modal" role="dialog" aria-modal="true" aria-labelledby="import-title">
          <div className="modal-heading"><div><span className="eyebrow">TEAM SHEET</span><h2 id="import-title">IMPORT <span>ROSTER</span></h2><p>Paste a WhatsApp list or spreadsheet text. Huddle will organize it for you to review.</p></div><button className="modal-close" onClick={() => setModalOpen(false)} aria-label="Close import modal">×</button></div>
          {!parsedPlayers ? <>
            <label className="textarea-label" htmlFor="roster-paste">PASTE ROSTER TEXT</label>
            <textarea id="roster-paste" className="roster-textarea" value={rosterText} onChange={(event) => setRosterText(event.target.value)} placeholder={'U10 Falcons\nAarav Shah - Parent: Riya Shah - 8 - 25 USD\nMia Patel, Kiran Patel, mia@example.com, jersey 12'} />
            <div className="modal-actions"><span>Emails are never guessed. Missing ones will be flagged.</span><button className="button button-primary" onClick={handleParse} disabled={parseBusy || !rosterText.trim()}>{parseBusy ? 'Parsing…' : 'Parse roster →'}</button></div>
          </> : <>
            {parseWarnings.length > 0 && <div className="parse-warning">⚠ {parseWarnings.join(' ')}</div>}
            <div className="edit-table-wrap"><table className="edit-table"><thead><tr><th>PLAYER</th><th>PARENT</th><th>PARENT EMAIL</th><th>JERSEY</th><th>FEE</th><th>GROUP</th><th /></tr></thead><tbody>
              {parsedPlayers.map((player, index) => <tr key={`${player.player_name}-${index}`}>
                <td><input value={player.player_name || ''} onChange={(event) => updateParsed(index, 'player_name', event.target.value)} aria-label="Player name" /></td>
                <td><input value={player.parent_name || ''} onChange={(event) => updateParsed(index, 'parent_name', event.target.value)} aria-label="Parent name" /></td>
                <td><input className={!player.parent_email ? 'missing-email' : ''} value={player.parent_email || ''} onChange={(event) => updateParsed(index, 'parent_email', event.target.value)} aria-label="Parent email" placeholder="Missing — add email" />{!player.parent_email && <small className="missing-label">EMAIL NEEDED</small>}</td>
                <td><input value={player.jersey_number || ''} onChange={(event) => updateParsed(index, 'jersey_number', event.target.value)} aria-label="Jersey number" /></td>
                <td><input type="number" min="0" step="0.01" value={player.amount ?? ''} onChange={(event) => updateParsed(index, 'amount', event.target.value)} aria-label="Amount" /></td>
                <td><input value={player.group || ''} onChange={(event) => updateParsed(index, 'group', event.target.value)} aria-label="Group" /></td>
                <td><button className="remove-player" onClick={() => setParsedPlayers((players) => players.filter((_, i) => i !== index))} aria-label={`Remove ${player.player_name}`}>×</button></td>
              </tr>)}
            </tbody></table></div>
            <div className="modal-actions review-actions"><button className="button button-quiet" onClick={() => setParsedPlayers(null)}>← Back to paste</button><span>{parsedPlayers.length} players · review and edit before saving</span><button className="button button-primary" onClick={handleSaveRoster} disabled={savingRoster || !parsedPlayers.length}>{savingRoster ? 'Saving…' : 'Save roster'}</button></div>
          </>}
        </section>
      </div>}
    </div>
  </AgGridProvider>
}

function summarizeResult(result) {
  if (result == null) return 'No result returned.'
  if (typeof result === 'string') return result
  if (result.created_count !== undefined) return `${result.created_count} draft invoices created. ${result.skipped?.length || 0} player(s) skipped; no invoices were sent.`
  if (result.queued_count !== undefined) return `${result.queued_count} reminder proposal(s) added to the Referee queue. Nothing was sent.`
  if (result.paid_invoices !== undefined) return `${result.paid_invoices} paid · ${result.unpaid_invoices} unpaid · ${result.overdue_invoices} overdue.`
  if (result.items && result.total_items !== undefined) return `${result.total_items} invoice records returned.`
  if (result.id && result.status) return `Invoice ${result.id} · ${result.status}.`
  return JSON.stringify(result).slice(0, 300)
}

function EmptyState({ title, text }) {
  return <div className="empty-state"><span>◌</span><strong>{title}</strong><p>{text}</p></div>
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>)
