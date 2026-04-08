import React, { useEffect, useState, useRef } from 'react';
import { marked } from 'marked';
import { api } from './api';

const EMPTY_ARTICLE = { image: '', badge_text: '', title: '', summary: '', meta: '', link: '', layout: 'image_left' };
const DEFAULT_LAYOUTS = ['hero','image_left','image_left','card_banner','image_left_tall'];
const MORE = '<!--more-->';

const DEFAULT_DATA = {
  org_name: '전인교육학회',
  org_subtitle: 'Academic Society for Human Completion',
  volume: '24',
  issue_date: '2026년 4월',
  web_view_url: 'https://humancompletion.org/',
  greeting: {
    photo: '', name: '이덕주', title: '전인교육학회 회장 · 명예교수',
    body: '회원 여러분, 따스한 봄 인사를 드립니다.', signature: '전인교육학회 회장 이덕주 드림',
  },
  articles: Array.from({ length: 5 }, (_, i) => ({ ...EMPTY_ARTICLE, layout: DEFAULT_LAYOUTS[i] })),
  footer: {
    address: '서울특별시 OO구 OO로 123 OO빌딩 4층',
    contact: 'Tel. 02-000-0000 · info@humancompletion.org',
    links: [
      { text: '홈페이지', url: 'https://humancompletion.org/' },
      { text: '학회소개', url: 'https://humancompletion.org/about' },
    ],
  },
};

// path 기반 deep set: "articles.2.title" → obj.articles[2].title = value
function setByPath(obj, path, value) {
  const parts = path.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const k = isNaN(parts[i]) ? parts[i] : parseInt(parts[i], 10);
    cur = cur[k];
  }
  const last = parts[parts.length - 1];
  cur[isNaN(last) ? last : parseInt(last, 10)] = value;
}

export default function App() {
  const [templates, setTemplates] = useState([]);
  const [senders, setSenders] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [template, setTemplate] = useState('classic');
  const [name, setName] = useState('새 뉴스레터');
  const [subject, setSubject] = useState('[전인교육학회] 뉴스레터');
  const [data, setData] = useState(DEFAULT_DATA);
  const [html, setHtml] = useState('');
  const [draftId, setDraftId] = useState(null);
  const [tab, setTab] = useState('edit');

  const [sender, setSender] = useState('mailhog');
  const [fromAddr, setFromAddr] = useState('noreply@humancompletion.org');
  const [fromName, setFromName] = useState('전인교육학회');
  const [recipients, setRecipients] = useState([]);
  const [sendStatus, setSendStatus] = useState('');
  const [testEmail, setTestEmail] = useState('');
  const [unsubModal, setUnsubModal] = useState(false);
  const [unsubList, setUnsubList] = useState([]);
  const [saveModal, setSaveModal] = useState(false);
  const [saveModalName, setSaveModalName] = useState('');

  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [viewport, setViewport] = useState('both'); // desktop | mobile | both
  const [editingDraftId, setEditingDraftId] = useState(null);
  const [editingDraftName, setEditingDraftName] = useState('');
  const [dragArticleIdx, setDragArticleIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const [manualContent, setManualContent] = useState('');

  // 본문/펼쳐보기 분리 상태 (data.greeting.body는 합쳐진 형태로 관리)
  const bodyParts = (data.greeting.body || '').split(MORE);
  const bodyMain = bodyParts[0] || '';
  const bodyMore = bodyParts[1] || '';

  const debounceRef = useRef();
  const iframeRef = useRef();
  const dataRef = useRef(data);
  const editingRef = useRef(false);

  useEffect(() => { dataRef.current = data; }, [data]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const DEFAULT_DRAFT_NAME = '260408 뉴스레터 (Vol.01)';
  useEffect(() => {
    api.templates().then(setTemplates).catch(() => {});
    api.senders().then(setSenders).catch(() => {});
    refreshUnsub();
    api.drafts().then(async list => {
      setDrafts(list);
      const def = list.find(d => d.name === DEFAULT_DRAFT_NAME);
      if (def) {
        const d = await api.draft(def.id);
        if (d.data?.articles) {
          d.data.articles = d.data.articles.map((a, i) => ({ ...a, layout: a.layout || DEFAULT_LAYOUTS[i] || 'image_left' }));
        }
        setDraftId(d.id);
        setName(d.name);
        setTemplate(d.template);
        setSubject(d.subject);
        setData(d.data);
      }
    }).catch(() => {});
  }, []);

  const refreshDrafts = () => api.drafts().then(setDrafts).catch(() => {});
  const refreshUnsub = () => api.unsubscribed().then(r => setUnsubList(r.emails || [])).catch(() => {});

  useEffect(() => {
    if (editingRef.current) return; // 미리보기 인라인 편집 중에는 재렌더 X
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      api.render(template, data).then(setHtml).catch(e => setHtml(`<pre>${e.message}</pre>`));
    }, 250);
  }, [template, data]);

  useEffect(() => {
    if (tab === 'manual' && !manualContent) {
      api.manual().then(r => setManualContent(r.content)).catch(() => setManualContent('# 매뉴얼을 불러올 수 없습니다.'));
    }
  }, [tab, manualContent]);

  const updateGreeting = (k, v) => setData(d => ({ ...d, greeting: { ...d.greeting, [k]: v } }));
  const updateArticle = (i, k, v) => setData(d => {
    const arr = [...d.articles]; arr[i] = { ...arr[i], [k]: v }; return { ...d, articles: arr };
  });
  const updateFooter = (k, v) => setData(d => ({ ...d, footer: { ...d.footer, [k]: v } }));

  const updateBody = (main, more) => {
    const combined = more ? `${main}${MORE}${more}` : main;
    updateGreeting('body', combined);
  };

  const onUploadImage = async (file, onUrl) => {
    try { const r = await api.uploadImage(file); onUrl(r.url); }
    catch (e) { alert('업로드 실패: ' + e.message); }
  };

  // === 미리보기 → 부모 통신 (이미지 드롭 + 텍스트 편집) ===
  const handlePreviewDrop = async (key, file) => {
    try {
      const r = await api.uploadImage(file);
      if (key === 'greeting') updateGreeting('photo', r.url);
      else if (key.startsWith('article-')) {
        const i = parseInt(key.split('-')[1], 10);
        updateArticle(i, 'image', r.url);
      }
    } catch (e) { alert('업로드 실패: ' + e.message); }
  };
  const handleFieldUpdate = (path, value) => {
    if (path === 'greeting.body_main' || path === 'greeting.body_more') {
      const cur = (dataRef.current.greeting.body || '').split(MORE);
      const main = path === 'greeting.body_main' ? value : (cur[0] || '');
      const more = path === 'greeting.body_more' ? value : (cur[1] || '');
      dataRef.current.greeting.body = more ? `${main}${MORE}${more}` : main;
      return;
    }
    setByPath(dataRef.current, path, value);
  };
  const handleEditStart = () => { editingRef.current = true; };
  const handleEditEnd = () => {
    editingRef.current = false;
    setData(JSON.parse(JSON.stringify(dataRef.current)));
  };
  useEffect(() => {
    window.__handlePreviewDrop = handlePreviewDrop;
    window.__updateField = handleFieldUpdate;
    window.__editStart = handleEditStart;
    window.__editEnd = handleEditEnd;
  });

  const onIframeLoad = () => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc) return;
    // 이미지 드롭
    doc.querySelectorAll('img[data-img]').forEach(img => {
      img.style.cursor = 'copy';
      img.addEventListener('dragover', e => {
        e.preventDefault();
        img.style.outline = '3px solid #1a6b4a';
        img.style.outlineOffset = '3px';
      });
      img.addEventListener('dragleave', () => { img.style.outline = ''; });
      img.addEventListener('drop', e => {
        e.preventDefault();
        img.style.outline = '';
        const f = e.dataTransfer.files?.[0];
        if (f && f.type.startsWith('image/')) {
          window.parent.__handlePreviewDrop(img.dataset.img, f);
        }
      });
    });
    // 미리보기 내 링크: 한 번 클릭은 무시(편집 가능), 더블클릭 시 새 탭
    doc.querySelectorAll('a[href]').forEach(a => {
      a.addEventListener('click', e => { e.preventDefault(); });
      a.addEventListener('dblclick', e => {
        e.preventDefault();
        const href = a.getAttribute('href');
        if (href && href !== '#') window.open(href, '_blank');
      });
      a.title = '더블클릭하여 링크 열기';
    });

    // 텍스트 인라인 편집 — plain text 필드와 HTML 필드 모두
    const bindEdit = (el, isHtml) => {
      el.contentEditable = 'true';
      el.spellcheck = false;
      el.style.outline = 'none';
      el.style.borderRadius = '3px';
      el.style.transition = 'box-shadow 120ms';
      el.addEventListener('mouseenter', () => {
        if (el !== doc.activeElement) el.style.boxShadow = '0 0 0 2px rgba(26,107,74,0.18)';
      });
      el.addEventListener('mouseleave', () => {
        if (el !== doc.activeElement) el.style.boxShadow = '';
      });
      el.addEventListener('focus', () => {
        window.parent.__editStart();
        el.style.boxShadow = '0 0 0 2px #1a6b4a';
      });
      el.addEventListener('input', () => {
        const key = isHtml ? el.dataset.fieldHtml : el.dataset.field;
        const value = isHtml ? el.innerHTML : el.innerText;
        window.parent.__updateField(key, value);
      });
      el.addEventListener('blur', () => {
        el.style.boxShadow = '';
        window.parent.__editEnd();
      });
      el.addEventListener('keydown', e => {
        if (!isHtml && e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); el.blur(); }
      });
    };
    doc.querySelectorAll('[data-field]').forEach(el => bindEdit(el, false));
    doc.querySelectorAll('[data-field-html]').forEach(el => bindEdit(el, true));
  };

  // 덮어쓰기 저장 (현재 초안에 저장). 새 초안일 땐 모달로 이름 받기
  const onSaveDraft = async () => {
    if (draftId) {
      await api.saveDraft({ id: draftId, name, template, subject, data });
      await refreshDrafts();
      setSendStatus('');
      // 가벼운 토스트 대신 짧은 알림
      const el = document.createElement('div');
      el.textContent = '✓ 저장됨';
      el.className = 'toast';
      document.body.appendChild(el);
      setTimeout(() => el.remove(), 1500);
    } else {
      setSaveModalName(name);
      setSaveModal(true);
    }
  };

  // 다른 이름으로 저장 — 항상 새 파일
  const onSaveDraftAs = () => {
    setSaveModalName(name);
    setSaveModal(true);
  };

  const confirmSave = async () => {
    const finalName = saveModalName.trim() || name;
    const d = await api.saveDraft({ name: finalName, template, subject, data });
    setDraftId(d.id);
    setName(finalName);
    setSaveModal(false);
    await refreshDrafts();
    setTab('drafts');
  };

  const onLoadDraft = async (id) => {
    const d = await api.draft(id);
    if (d.data?.articles) {
      d.data.articles = d.data.articles.map((a, i) => ({ ...a, layout: a.layout || DEFAULT_LAYOUTS[i] || 'image_left' }));
    }
    setDraftId(d.id); setName(d.name); setTemplate(d.template); setSubject(d.subject); setData(d.data);
    setTab('edit');
  };

  const onExportHtml = async () => {
    const blob = await api.exportHtml(template, data);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `newsletter_${template}.html`; a.click();
    URL.revokeObjectURL(url);
  };

  const onParseRecipients = async (file) => {
    const r = await api.parseRecipients(file);
    setRecipients(r.recipients);
  };

  const onSend = async () => {
    if (!recipients.length) { alert('수신자 CSV를 먼저 업로드하세요'); return; }
    if (!confirm(`${recipients.length}명에게 [${sender}]로 발송할까요?`)) return;
    setSendStatus('발송 중...');
    try {
      const r = await api.send({ sender, template, subject, from_addr: fromAddr, from_name: fromName, recipients, data });
      const skippedTxt = r.skipped ? ` · ${r.skipped}건 수신거부 제외` : '';
      setSendStatus(`✓ ${r.sent}건 성공 / ${r.failed}건 실패${skippedTxt}` + (r.errors.length ? '\n\n' + r.errors.join('\n') : ''));
    } catch (e) { setSendStatus('실패: ' + e.message); }
  };

  const onTestSend = async () => {
    if (!testEmail || !testEmail.includes('@')) { alert('테스트 발송할 이메일 주소를 입력하세요'); return; }
    setSendStatus('테스트 발송 중...');
    try {
      const r = await api.send({ sender, template, subject, from_addr: fromAddr, from_name: fromName, recipients: [{ email: testEmail }], data });
      setSendStatus(`테스트 ${r.sent ? '✓ 성공' : '✗ 실패'} → ${testEmail}` + (r.errors.length ? '\n\n' + r.errors.join('\n') : ''));
    } catch (e) { setSendStatus('실패: ' + e.message); }
  };

  const Icon = ({ name, size = 16 }) => {
    const s = { width: size, height: size, fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round' };
    const paths = {
      edit: <><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/></>,
      drafts: <><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16"/><path d="M9 4v5"/></>,
      send: <><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/></>,
      save: <><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></>,
      download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></>,
      mail: <><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 6l-10 7L2 6"/></>,
      bolt: <><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></>,
      check: <><path d="M20 6L9 17l-5-5"/></>,
      eye: <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>,
      sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></>,
      moon: <><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></>,
      chevronLeft: <><path d="M15 18l-6-6 6-6"/></>,
      chevronRight: <><path d="M9 18l6-6-6-6"/></>,
      monitor: <><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></>,
      smartphone: <><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/></>,
      split: <><rect x="2.5" y="5" width="13" height="14" rx="1.5"/><rect x="17" y="7" width="4.5" height="10" rx="1"/></>,
      grip: <><circle cx="9" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="18" r="1"/></>,
      copy: <><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></>,
      book: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></>,
    };
    return <svg viewBox="0 0 24 24" style={s}>{paths[name]}</svg>;
  };

  const Dropzone = ({ onFile, hint = 'JPG, PNG · 최대 10MB', accept = 'image/*', validate }) => {
    const [drag, setDrag] = useState(false);
    const isValid = (f) => {
      if (validate) return validate(f);
      return f.type.startsWith('image/');
    };
    return (
      <div
        className={`dropzone${drag ? ' dragging' : ''}`}
        onDragOver={e => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => {
          e.preventDefault(); setDrag(false);
          const f = e.dataTransfer.files?.[0];
          if (f && isValid(f)) onFile(f);
        }}
      >
        <div className="dropzone-icon"><Icon name="download" size={16}/></div>
        <div className="dropzone-text">파일을 끌어다 놓거나 <strong>클릭하여 업로드</strong></div>
        <div className="dropzone-hint">{hint}</div>
        <input type="file" accept={accept} onChange={e => e.target.files[0] && onFile(e.target.files[0])} />
      </div>
    );
  };

  const RailBtn = ({ id, icon, label }) => (
    <button className={tab === id ? 'active' : ''} onClick={() => setTab(id)} title={label}>
      <Icon name={icon} size={24} />
      <span className="rail-label">{label}</span>
    </button>
  );

  return (
    <div className={`app${tab === 'edit' && panelCollapsed ? ' panel-collapsed' : ''}`}>
      <div className="logo-cell">전</div>

      <div className="topbar">
        <div className="topbar-title">
          <span className="dot"></span>
          <strong>전인교육학회 뉴스레터 스튜디오</strong>
          <span className="topbar-sub">· {name}</span>
        </div>
        <div className="topbar-actions">
          <div className="template-switcher">
            {templates.map(t => (
              <button key={t.key} className={template === t.key ? 'active' : ''} onClick={() => setTemplate(t.key)}>
                {t.key === 'classic' ? 'Classic' : t.key === 'magazine' ? 'Magazine' : 'Minimal'}
              </button>
            ))}
          </div>
          <button className="icon-only secondary sm" title={theme === 'dark' ? '라이트 모드' : '다크 모드'} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={15}/>
          </button>
          <button className="secondary sm" onClick={onExportHtml}><Icon name="download"/> HTML 내보내기</button>
          <button className="secondary sm wide" onClick={onSaveDraftAs} title="새 파일로 저장"><Icon name="copy"/> 다른 이름으로 저장</button>
          <button className="sm" onClick={onSaveDraft}><Icon name="save"/> 저장</button>
        </div>
      </div>

      <div className="rail">
        <RailBtn id="edit" icon="edit" label="편집" />
        <RailBtn id="drafts" icon="drafts" label="초안" />
        <RailBtn id="send" icon="send" label="발송" />
        <div style={{ flex: 1 }}/>
        <RailBtn id="manual" icon="book" label="매뉴얼" />
      </div>

      <div className="panel">
        <div className="panel-header">
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
            <div>
              {tab === 'edit' && (<><h2>뉴스레터 편집</h2><p>회장 인사말 + 5개 아티클을 작성하세요. 미리보기 텍스트는 직접 클릭해 수정할 수도 있습니다.</p></>)}
              {tab === 'drafts' && (<><h2>저장된 초안</h2><p>이전에 작성한 뉴스레터를 불러오거나 삭제할 수 있습니다.</p></>)}
              {tab === 'send' && (<><h2>발송 설정</h2><p>발송 방식과 수신자를 선택한 뒤 테스트 또는 전체 발송하세요.</p></>)}
              {tab === 'manual' && (<><h2>사용 매뉴얼</h2><p>기능별 사용법과 자주 묻는 질문을 확인하세요.</p></>)}
            </div>
            {tab === 'edit' && (
              <button className="icon-only secondary sm" title="편집 패널 접기" onClick={() => setPanelCollapsed(true)}>
                <Icon name="chevronLeft" size={14}/>
              </button>
            )}
          </div>
        </div>

        <div className="panel-inner">
          {tab === 'edit' && (
            <>
              <div className="section">
                <div className="section-title">기본 정보</div>
                <label>초안 이름</label>
                <input value={name} onChange={e=>setName(e.target.value)} />
                <label>메일 제목</label>
                <input value={subject} onChange={e=>setSubject(e.target.value)} />
                <div className="row">
                  <div><label>학회명 (한글)</label><input value={data.org_name || ''} onChange={e=>setData(d=>({...d,org_name:e.target.value}))} /></div>
                  <div><label>영문명</label><input value={data.org_subtitle || ''} onChange={e=>setData(d=>({...d,org_subtitle:e.target.value}))} /></div>
                </div>
                <div className="row">
                  <div><label>호수 (Vol.)</label><input value={data.volume} onChange={e=>setData(d=>({...d,volume:e.target.value}))} /></div>
                  <div><label>발행일</label><input value={data.issue_date} onChange={e=>setData(d=>({...d,issue_date:e.target.value}))} /></div>
                </div>
                <label>웹에서 보기 URL</label>
                <input value={data.web_view_url} onChange={e=>setData(d=>({...d,web_view_url:e.target.value}))} />
              </div>

              <div className="section">
                <div className="section-title">회장 인사말</div>
                <label>프로필 사진</label>
                <input value={data.greeting.photo} onChange={e=>updateGreeting('photo', e.target.value)} placeholder="https://..." />
                <Dropzone onFile={file=>onUploadImage(file, url=>updateGreeting('photo', url))} hint="권장 160×160 (정사각)" />
                {data.greeting.photo && <img src={data.greeting.photo} className="thumb" alt="" />}
                <div className="row">
                  <div><label>이름</label><input value={data.greeting.name} onChange={e=>updateGreeting('name', e.target.value)} /></div>
                  <div><label>직함</label><input value={data.greeting.title} onChange={e=>updateGreeting('title', e.target.value)} /></div>
                </div>
                <label>본문 <span className="muted">(항상 표시 · 엔터키로 줄바꿈)</span></label>
                <textarea rows={5} value={bodyMain} onChange={e=>updateBody(e.target.value, bodyMore)} />
                <label>펼쳐보기 내용 <span className="muted">(접혀 있다가 클릭 시 표시)</span></label>
                <textarea rows={4} value={bodyMore} onChange={e=>updateBody(bodyMain, e.target.value)} placeholder="비워두면 펼쳐보기 버튼이 나오지 않습니다" />
                <label>서명</label>
                <input value={data.greeting.signature} onChange={e=>updateGreeting('signature', e.target.value)} />
              </div>

              <div className="section">
                <div className="section-title">아티클 5개</div>
                <p className="muted" style={{ marginBottom: 10 }}>좌측 ⋮⋮ 핸들을 드래그해서 순서를 바꿀 수 있습니다.</p>
                {data.articles.map((a, i) => (
                  <div
                    className={`article-card${dragArticleIdx === i ? ' dragging' : ''}${dragOverIdx === i && dragArticleIdx !== null && dragArticleIdx !== i ? ' drop-target' : ''}`}
                    key={i}
                    onDragOver={e => { e.preventDefault(); if (dragOverIdx !== i) setDragOverIdx(i); }}
                    onDragLeave={() => { if (dragOverIdx === i) setDragOverIdx(null); }}
                    onDrop={e => {
                      e.preventDefault();
                      const from = dragArticleIdx;
                      setDragOverIdx(null);
                      if (from === null || from === i) return;
                      setData(d => {
                        const arr = [...d.articles];
                        const [moved] = arr.splice(from, 1);
                        arr.splice(i, 0, moved);
                        return { ...d, articles: arr };
                      });
                      setDragArticleIdx(null);
                    }}
                  >
                    <div className="article-card-head">
                      <div className="article-num">
                        <span
                          className="drag-handle"
                          draggable
                          onDragStart={e => { setDragArticleIdx(i); e.dataTransfer.effectAllowed = 'move'; }}
                          onDragEnd={() => { setDragArticleIdx(null); setDragOverIdx(null); }}
                          title="드래그하여 순서 변경"
                        >
                          <Icon name="grip" size={16}/>
                        </span>
                        <span className="badge">{i+1}</span> Article
                      </div>
                    </div>
                    <label>이미지</label>
                    <input value={a.image} onChange={e=>updateArticle(i, 'image', e.target.value)} placeholder="https://..." />
                    <Dropzone onFile={file=>onUploadImage(file, url=>updateArticle(i, 'image', url))} hint="권장 1080px 폭 · 3:2 비율" />
                    {a.image && <img src={a.image} className="thumb" alt="" />}
                    <label>카테고리 뱃지</label>
                    <input value={a.badge_text} onChange={e=>updateArticle(i, 'badge_text', e.target.value)} />
                    <label>제목</label>
                    <input value={a.title} onChange={e=>updateArticle(i, 'title', e.target.value)} />
                    <label>요약</label>
                    <textarea rows={3} value={a.summary} onChange={e=>updateArticle(i, 'summary', e.target.value)} />
                    <div className="row">
                      <div><label>메타 (작성자/날짜)</label><input value={a.meta} onChange={e=>updateArticle(i, 'meta', e.target.value)} /></div>
                      <div><label>링크</label><input value={a.link} onChange={e=>updateArticle(i, 'link', e.target.value)} /></div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="section">
                <div className="section-title">푸터</div>
                <label>주소</label>
                <input value={data.footer.address} onChange={e=>updateFooter('address', e.target.value)} />
                <label>연락처</label>
                <input value={data.footer.contact} onChange={e=>updateFooter('contact', e.target.value)} />
              </div>

            </>
          )}

          {tab === 'drafts' && (
            <div className="section">
              {drafts.length === 0 && (
                <div className="empty">
                  <div className="icon"><Icon name="drafts" size={36}/></div>
                  저장된 초안이 없습니다
                </div>
              )}
              {drafts.map(d => (
                <div className="draft-item" key={d.id}>
                  <div className="draft-item-info">
                    {editingDraftId === d.id ? (
                      <input
                        autoFocus
                        className="draft-name-input"
                        value={editingDraftName}
                        onChange={e=>setEditingDraftName(e.target.value)}
                        onBlur={async ()=>{
                          await api.renameDraft(d.id, editingDraftName);
                          if (draftId === d.id) setName(editingDraftName);
                          setEditingDraftId(null);
                          refreshDrafts();
                        }}
                        onKeyDown={async e=>{
                          if (e.key === 'Enter') {
                            await api.renameDraft(d.id, editingDraftName);
                            if (draftId === d.id) setName(editingDraftName);
                            setEditingDraftId(null);
                            refreshDrafts();
                          }
                          if (e.key === 'Escape') setEditingDraftId(null);
                        }}
                      />
                    ) : (
                      <div className="draft-item-name" onDoubleClick={()=>{ setEditingDraftId(d.id); setEditingDraftName(d.name); }} title="더블클릭하여 이름 변경">{d.name}</div>
                    )}
                    <div className="draft-item-meta">{d.id} · {d.template}</div>
                  </div>
                  <div className="draft-item-actions">
                    <button className="secondary sm" onClick={()=>onLoadDraft(d.id)}>불러오기</button>
                    <button className="danger sm" onClick={async ()=>{ if(confirm('삭제하시겠습니까?')){ await api.deleteDraft(d.id); refreshDrafts(); }}}>삭제</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === 'send' && (
            <>
              <div className="section">
                <div className="section-title">발신자</div>
                <label>발송 서비스</label>
                <select value={sender} onChange={e=>setSender(e.target.value)}>
                  {senders.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                </select>
                <div className="row">
                  <div><label>발신 이메일</label><input value={fromAddr} onChange={e=>setFromAddr(e.target.value)} /></div>
                  <div><label>발신자 이름</label><input value={fromName} onChange={e=>setFromName(e.target.value)} /></div>
                </div>
              </div>

              <div className="section">
                <div className="section-title">테스트 발송</div>
                <p className="muted" style={{ marginBottom: 8 }}>전체 발송 전에 본인 이메일에 먼저 보내 확인하는 것을 권장합니다.</p>
                <div className="inline-send">
                  <input
                    type="email"
                    placeholder="test@example.com"
                    value={testEmail}
                    onChange={e=>setTestEmail(e.target.value)}
                    onKeyDown={e=>{ if (e.key === 'Enter') onTestSend(); }}
                  />
                  <button className="secondary" onClick={onTestSend}><Icon name="mail" size={14}/> 테스트 발송</button>
                </div>
              </div>

              <div className="section">
                <div className="section-title">수신자 명단</div>
                <p className="muted" style={{ marginBottom: 8 }}>컬럼: <code>email</code> 또는 <code>email,name</code> · CSV / Excel(.xlsx) 지원</p>
                <Dropzone
                  onFile={onParseRecipients}
                  accept=".csv,.txt,.xlsx,.xlsm"
                  hint="CSV 또는 Excel 파일을 드래그하거나 클릭하여 업로드"
                  validate={f => /\.(csv|txt|xlsx|xlsm)$/i.test(f.name)}
                />
                {recipients.length > 0 && (
                  <div className="recipients-pill"><Icon name="check" size={12}/> {recipients.length}명 로드됨</div>
                )}
              </div>

              <div className="section">
                <div className="section-title">수신거부 명단</div>
                <p className="muted" style={{ marginBottom: 8 }}>수신거부한 이메일은 발송 시 자동으로 제외됩니다.</p>
                <button className="secondary" style={{ width: '100%' }} onClick={() => { refreshUnsub(); setUnsubModal(true); }}>
                  <Icon name="drafts" size={14}/> 수신거부 명단 보기 ({unsubList.length}명)
                </button>
              </div>

              <div className="dispatch-card">
                <div className="dispatch-card-head">
                  <div className="dispatch-card-title">전체 발송</div>
                  <div className="dispatch-card-meta">{senders.find(s=>s.key===sender)?.label || sender}</div>
                </div>
                <div className="dispatch-card-stats">
                  <div className="stat">
                    <div className="stat-num">{recipients.length}</div>
                    <div className="stat-label">수신자</div>
                  </div>
                  <div className="stat">
                    <div className="stat-num">{template.charAt(0).toUpperCase() + template.slice(1)}</div>
                    <div className="stat-label">템플릿</div>
                  </div>
                </div>
                <button className="dispatch-btn" onClick={onSend} disabled={!recipients.length}>
                  <Icon name="send" size={15}/>
                  <span>{recipients.length ? `${recipients.length}명에게 발송하기` : '수신자를 먼저 업로드하세요'}</span>
                </button>
                {sendStatus && <div className="status-box">{sendStatus}</div>}
              </div>
            </>
          )}

          {tab === 'manual' && (
            <div className="manual" dangerouslySetInnerHTML={{ __html: marked.parse(manualContent || '# 불러오는 중...') }} />
          )}
        </div>
      </div>

      {saveModal && (
        <div className="modal-backdrop" onClick={()=>setSaveModal(false)}>
          <div className="modal" onClick={e=>e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-icon"><Icon name="save" size={20}/></div>
              <div>
                <div className="modal-title">초안 저장</div>
                <div className="modal-sub">이 뉴스레터를 식별할 이름을 입력하세요.</div>
              </div>
            </div>
            <div className="modal-body">
              <label>메일 이름</label>
              <input
                autoFocus
                value={saveModalName}
                onChange={e=>setSaveModalName(e.target.value)}
                onKeyDown={e=>{ if(e.key==='Enter') confirmSave(); if(e.key==='Escape') setSaveModal(false); }}
                placeholder="예: 2026년 4월호 뉴스레터"
              />
              <div className="modal-meta">
                <span><Icon name="drafts" size={11}/> 템플릿: <strong>{template}</strong></span>
                <span>· 같은 이름이 있으면 (2), (3)...이 자동 부여됩니다</span>
              </div>
            </div>
            <div className="modal-footer">
              <button className="secondary" onClick={()=>setSaveModal(false)}>취소</button>
              <button onClick={confirmSave}><Icon name="check"/> 저장</button>
            </div>
          </div>
        </div>
      )}

      {unsubModal && (
        <div className="modal-backdrop" onClick={()=>setUnsubModal(false)}>
          <div className="modal" style={{ width: 520 }} onClick={e=>e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-icon"><Icon name="mail" size={20}/></div>
              <div>
                <div className="modal-title">수신거부 명단</div>
                <div className="modal-sub">총 {unsubList.length}명 · 발송 시 자동으로 제외됩니다.</div>
              </div>
            </div>
            <div className="modal-body" style={{ maxHeight: '50vh', overflowY: 'auto' }}>
              {unsubList.length === 0 ? (
                <div className="empty"><div className="icon"><Icon name="check" size={36}/></div>수신거부한 회원이 없습니다</div>
              ) : (
                unsubList.map(email => (
                  <div className="draft-item" key={email}>
                    <div className="draft-item-info">
                      <div className="draft-item-name" style={{ fontFamily: "'SF Mono', Menlo, monospace", fontSize: 12 }}>{email}</div>
                    </div>
                    <button className="danger sm" onClick={async ()=>{ await api.removeUnsubscribed(email); refreshUnsub(); }}>해제</button>
                  </div>
                ))
              )}
            </div>
            <div className="modal-footer">
              <button className="secondary" onClick={()=>setUnsubModal(false)}>닫기</button>
            </div>
          </div>
        </div>
      )}

      {tab === 'edit' && panelCollapsed && (
        <button className="panel-expand-handle" onClick={() => setPanelCollapsed(false)} title="편집 패널 펼치기">
          <Icon name="chevronRight" size={14}/>
        </button>
      )}

      <div className="preview">
        <div className="preview-toolbar">
          <div className="viewport-switcher">
            <button className={viewport === 'both' ? 'active' : ''} onClick={() => setViewport('both')} title="PC + 모바일 동시"><Icon name="split" size={14}/></button>
            <button className={viewport === 'desktop' ? 'active' : ''} onClick={() => setViewport('desktop')} title="PC만"><Icon name="monitor" size={13}/></button>
            <button className={viewport === 'mobile' ? 'active' : ''} onClick={() => setViewport('mobile')} title="모바일만"><Icon name="smartphone" size={13}/></button>
          </div>
        </div>
        <div className="preview-frames">
          {(viewport === 'desktop' || viewport === 'both') && (
            <div className={`preview-frame ${viewport === 'both' ? 'both-desktop' : 'desktop'}`}>
              <div className="preview-bar">
                <div className="preview-dots"><span></span><span></span><span></span></div>
                <span className="preview-label"><Icon name="monitor" size={12}/> Desktop · {template.toUpperCase()}</span>
              </div>
              <iframe ref={iframeRef} srcDoc={html} title="preview-desktop" onLoad={onIframeLoad} />
            </div>
          )}
          {(viewport === 'mobile' || viewport === 'both') && (
            <div className={`preview-frame ${viewport === 'both' ? 'both-mobile' : 'mobile'}`}>
              <div className="preview-bar">
                <div className="preview-dots"><span></span><span></span><span></span></div>
                <span className="preview-label"><Icon name="smartphone" size={12}/> Mobile · 390px</span>
              </div>
              <iframe srcDoc={html} title="preview-mobile" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
