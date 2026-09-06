"""Shared HTML for both demo consoles. mode='url' or mode='local'."""


def page(mode: str) -> str:
    is_url = mode == "url"
    title = "StateScout Audit Console" if is_url else "StateScout Local Audit"
    h1 = "Audit console" if is_url else "Local site audit"
    if is_url:
        lede = ("Give a URL and a plain-English access policy for one role. The crawler explores the "
                "site, a Gemini vision pass and a deterministic negation engine check every state "
                "against the policy, and the exploration graph is stored in Neo4j.")
        input_html = (
            '<label for="target">Website URL</label>'
            '<input id="target" type="url" required placeholder="https://example.com">'
        )
        examples_html = ""
        hint = ("The crawl stays on the URL's own origin. With vision on, each state is one Gemini "
                "call (free tier is limited); a rate-limited run still finishes on the deterministic parse.")
    else:
        lede = ("Point it at a folder on this machine that holds a static site — an index.html plus "
                "linked pages. It serves the folder locally, the crawler explores it, and a Gemini "
                "vision pass plus a deterministic negation engine check every page against your policy.")
        input_html = (
            '<label for="target">Folder on this machine</label>'
            '<input id="target" required placeholder="/Users/you/my-site  or  ./build">'
            '<p class="ex" id="ex"></p>'
            '<label for="entry">Entry file (optional)</label>'
            '<input id="entry" placeholder="index.html — leave blank to auto-detect">'
        )
        examples_html = """
  fetch("/api/examples").then(r=>r.json()).then(d=>{
    if(!d.names||!d.names.length) return;
    document.querySelector("#ex").innerHTML = "bundled examples: " +
      d.names.map(n=>`<a data-p="${d.root}/${n}">${n}</a>`).join(" · ");
    document.querySelectorAll("#ex a").forEach(a=>a.addEventListener("click",()=>{document.querySelector("#target").value=a.dataset.p;}));
  });"""
        hint = ("The whole crawl is local — the served folder never leaves this machine. With vision on, "
                "each state is one Gemini call (free tier is limited); a rate-limited run still finishes "
                "on the deterministic parse alone.")

    entry_field = 'entry:document.querySelector("#entry")?document.querySelector("#entry").value:"",' if not is_url else ""
    body_key = "url" if is_url else "path"

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  window._mermaid = mermaid;
</script>
<style>
  :root{{
    --ground:#f5f6f8;--surface:#fff;--surface-2:#eef0f3;--ink:#161a1f;--muted:#5b6572;
    --border:#e1e4e9;--accent:#1f6feb;
    --crit:#c5322a;--crit-bg:#fbeae8;--crit-line:#e0a59f;
    --warn:#9a6410;--warn-bg:#f8efdb;--warn-line:#dcc493;
    --pass:#177f4e;--pass-bg:#e4f3ea;--pass-line:#a9d4bd;
    --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
    --mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,monospace;
  }}
  @media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
    --ground:#0d1117;--surface:#161b22;--surface-2:#1b212b;--ink:#e7eaef;--muted:#8b939f;
    --border:#293039;--accent:#4f8fff;
    --crit:#f0736a;--crit-bg:#2a1411;--crit-line:#6e2f2a;
    --warn:#e2ab45;--warn-bg:#2a2210;--warn-line:#6a5220;
    --pass:#48b581;--pass-bg:#0e241a;--pass-line:#265440;
  }}}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.55}}
  .wrap{{max-width:940px;margin:0 auto;padding:44px 24px 80px}}
  code{{font-family:var(--mono);font-size:.88em;background:var(--surface-2);padding:1px 5px;border-radius:4px}}
  h1{{font-size:25px;font-weight:600;letter-spacing:-.01em;margin:0 0 6px}}
  .wordmark{{font-family:var(--mono);font-weight:600;font-size:12px;letter-spacing:.13em;text-transform:uppercase;color:var(--accent)}}
  .lede{{color:var(--muted);max-width:64ch;margin:6px 0 0}}
  .disclose{{font-size:12px;color:var(--muted);margin-top:14px;border-left:3px solid var(--warn);padding:6px 0 6px 12px}}
  form{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:22px 24px;margin:28px 0}}
  label{{display:block;font-family:var(--mono);font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}}
  input,textarea{{width:100%;font-family:var(--sans);font-size:14px;color:var(--ink);background:var(--ground);border:1px solid var(--border);border-radius:7px;padding:9px 11px;margin-bottom:16px}}
  textarea{{min-height:64px;resize:vertical}}
  .row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}}
  @media(max-width:600px){{.row{{grid-template-columns:1fr}}}}
  button{{font-family:var(--sans);font-weight:600;font-size:14px;color:#fff;background:var(--accent);border:0;border-radius:7px;padding:10px 20px;cursor:pointer}}
  button:disabled{{opacity:.5;cursor:not-allowed}}
  .hint,.ex{{font-size:11.5px;color:var(--muted);margin:-8px 0 16px}}
  .ex a{{color:var(--accent);cursor:pointer;text-decoration:underline}}
  .panel{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px 22px;margin-top:20px}}
  .eyebrow{{font-family:var(--mono);font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);display:block;margin-bottom:12px}}
  .log{{font-family:var(--mono);font-size:12px;background:var(--ground);border:1px solid var(--border);border-radius:8px;padding:12px 14px;max-height:260px;overflow:auto;white-space:pre-wrap;line-height:1.7}}
  .log .v{{color:var(--crit);font-weight:600}}
  .spinner{{display:inline-block;width:11px;height:11px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;margin-right:8px;vertical-align:middle}}
  @keyframes spin{{to{{transform:rotate(360deg)}}}}
  @media(prefers-reduced-motion:reduce){{.spinner{{animation:none}}}}
  .tiles{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--border);border:1px solid var(--border);border-radius:10px;overflow:hidden}}
  .tile{{background:var(--surface);padding:14px 16px}}
  .tile-n{{font-family:var(--mono);font-size:23px;font-weight:600;font-variant-numeric:tabular-nums;display:block}}
  .tile-l{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:2px;display:block}}
  .tile--flag .tile-n{{color:var(--crit)}} .tile--pass .tile-n{{color:var(--pass)}}
  .parsed{{font-size:13px;margin:14px 0 0}}
  .parsed .k{{font-family:var(--mono);font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
  .note{{font-size:12px;color:var(--muted);margin-top:6px}}
  .viol{{background:var(--crit-bg);border-left:3px solid var(--crit);border-radius:0 8px 8px 0;padding:14px 16px;margin-top:12px}}
  .viol--warn{{background:var(--warn-bg);border-left-color:var(--warn)}}
  .chip{{font-family:var(--mono);font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:4px;color:#fff}}
  .chip--crit{{background:var(--crit)}} .chip--warn{{background:var(--warn)}}
  .viol-why{{font-weight:500;margin:8px 0 3px;font-size:13px}}
  .viol-ev{{font-size:12px;color:var(--muted);margin:0 0 10px}}
  .viol-ev code{{background:var(--surface)}}
  img.shot{{width:100%;border:1px solid var(--border);border-radius:6px;display:block;margin-top:4px}}
  .clean{{background:var(--pass-bg);border-left:3px solid var(--pass);border-radius:0 8px 8px 0;padding:14px 16px;font-size:13px}}
  .clean strong{{color:var(--pass)}}
  .pages{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:12px}}
  .pg{{border:1px solid var(--border);border-radius:8px;overflow:hidden;background:var(--surface)}}
  .pg img{{width:100%;display:block;border-bottom:1px solid var(--border)}}
  .pg span{{display:block;font-family:var(--mono);font-size:10.5px;color:var(--muted);padding:6px 8px;word-break:break-all}}
  .vision{{font-size:12px;color:var(--muted);margin-top:12px}}
  .vision-tag{{font-family:var(--mono);font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:var(--accent);border:1px solid var(--border);padding:1px 5px;border-radius:4px;margin-right:6px}}
  .err{{font-family:var(--mono);font-size:12px;color:var(--crit);white-space:pre-wrap}}
</style></head>
<body><div class="wrap">
  <span class="wordmark">StateScout AI</span>
  <h1>{h1}</h1>
  <p class="lede">{lede}</p>
  <p class="disclose">Real stack at ~60%. Local stand-ins: the ADR-001 C-3 <code>state_id</code> fix and a
    Gemini-backed policy parser filling in for Track B's unbuilt FR-04 parser. The negation engine only
    recognises the subjects <code>admin-access, debug-access, export-data, delete-user, logout, login</code>.</p>

  <form id="f">
    {input_html}
    <label for="policy">Policy (one role, plain English)</label>
    <textarea id="policy" required placeholder="A guest must never see an admin panel."></textarea>
    <div class="row">
      <div><label for="role">Role</label><input id="role" value="guest"></div>
      <div><label for="ms">Max states</label><input id="ms" type="number" value="15" min="1" max="40"></div>
      <div><label for="dl">Depth limit</label><input id="dl" type="number" value="3" min="0" max="6"></div>
    </div>
    <label style="display:flex;align-items:center;gap:8px;text-transform:none;letter-spacing:0;font-size:13px;color:var(--ink);margin-bottom:14px">
      <input id="vis" type="checkbox" checked style="width:auto;margin:0"> Gemini vision pass on every state
    </label>
    <p class="hint">{hint}</p>
    <button id="go" type="submit">Run audit</button>
  </form>
  <div id="out"></div>
</div>
<script>
const $=s=>document.querySelector(s);const out=$("#out");
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]));
{examples_html}
$("#f").addEventListener("submit",async e=>{{
  e.preventDefault();$("#go").disabled=true;
  out.innerHTML=`<div class="panel"><span class="eyebrow">Running</span><div id="log" class="log"><span class="spinner"></span>starting…</div></div>`;
  let job;
  try{{
    const r=await fetch("/api/audit",{{method:"POST",headers:{{"content-type":"application/json"}},body:JSON.stringify({{
      {body_key}:$("#target").value,{entry_field}policy:$("#policy").value,role:$("#role").value,
      max_states:+$("#ms").value,depth_limit:+$("#dl").value,use_vision:$("#vis").checked
    }})}});
    job=(await r.json()).job_id;
  }}catch(err){{out.innerHTML=`<div class="panel err">could not start: ${{esc(err)}}</div>`;$("#go").disabled=false;return;}}
  const poll=setInterval(async()=>{{
    const s=await(await fetch("/api/audit/"+job)).json();
    const l=$("#log");
    if(l)l.innerHTML=(s.status==="done"||s.status==="error"?"":`<span class="spinner"></span>`)+
      s.log.map(x=>x.startsWith("VIOLATION")||x.startsWith("ERROR")?`<span class="v">${{esc(x)}}</span>`:esc(x)).join("\\n");
    if(l)l.scrollTop=l.scrollHeight;
    if(s.status==="done"){{clearInterval(poll);render(s);$("#go").disabled=false;}}
    if(s.status==="error"){{clearInterval(poll);out.innerHTML+=`<div class="panel"><span class="eyebrow">Error</span><div class="err">${{esc(s.error)}}</div></div>`;$("#go").disabled=false;}}
  }},1500);
}});
function render(s){{
  const r=s.result,pp=s.policy_parsed||{{}};const clean=r.violations.length===0;
  let h=`<div class="panel"><span class="eyebrow">Result — ${{esc(r.target)}} as “${{esc(r.role)}}”</span>
    <div class="tiles">
      <div class="tile"><span class="tile-n">${{r.states}}</span><span class="tile-l">states</span></div>
      <div class="tile"><span class="tile-n">${{r.edges}}</span><span class="tile-l">action edges</span></div>
      <div class="tile"><span class="tile-n">${{r.vision_calls}}</span><span class="tile-l">vision calls</span></div>
      <div class="tile"><span class="tile-n">${{(r.duration_ms/1000).toFixed(1)}}s</span><span class="tile-l">crawl time</span></div>
      <div class="tile"><span class="tile-n">${{r.skipped}}</span><span class="tile-l">dead ends</span></div>
      <div class="tile ${{clean?'tile--pass':'tile--flag'}}"><span class="tile-n">${{r.violations.length}}</span><span class="tile-l">violations</span></div>
    </div>
    <p class="parsed"><span class="k">policy parsed as</span><br>
      forbidden: <code>${{(pp.forbidden||[]).join(", ")||"—"}}</code> &nbsp; required: <code>${{(pp.required||[]).join(", ")||"—"}}</code></p>
    ${{(pp.notes||[]).map(n=>`<p class="note">${{esc(n)}}</p>`).join("")}}
    <p class="parsed"><span class="k">ended</span> <code>${{esc(r.termination_reason)}}</code> — graph is cyclic, revisits kept as back-edges.</p>`;
  if(r.vision_calls===0&&r.vision_failed===0) h+=`<p class="vision"><span class="vision-tag">Gemini vision</span> off — deterministic DOM/AX parse only.</p>`;
  else if(r.vision_failed) h+=`<p class="vision"><span class="vision-tag">Gemini vision</span> ${{r.vision_calls}} ok, ${{r.vision_failed}} rate-limited — those states used the deterministic parse. <code>${{esc(r.vision_error||"")}}</code></p>`;
  else if(r.vision_added&&r.vision_added.length) h+=r.vision_added.map(a=>`<p class="vision"><span class="vision-tag">Gemini vision</span> added <code>${{esc(a.caps.join(", "))}}</code> from a screenshot the DOM text did not carry.</p>`).join("");
  else h+=`<p class="vision"><span class="vision-tag">Gemini vision</span> ran on every state (${{r.vision_calls}} calls); its reading matched the DOM parser.</p>`;
  if(clean) h+=`<div class="clean" style="margin-top:14px"><strong>No violations.</strong> Nothing the policy forbids was present for this role, and everything it requires was reachable.</div>`;
  else h+=r.violations.map(v=>{{
    const w=v.clause_type==="required_absent";
    const ev=[v.evidence_text?`text <code>${{esc(v.evidence_text)}}</code>`:null,v.evidence_selector?`selector <code>${{esc(v.evidence_selector)}}</code>`:null].filter(Boolean).join(" · ")||"no element to point at — this is an <em>absence</em>";
    return `<div class="viol ${{w?'viol--warn':''}}"><span class="chip ${{w?'chip--warn':'chip--crit'}}">${{w?'FR-19 · required absent':'FR-18 · forbidden present'}}</span>
      <p class="viol-why">${{esc(v.rationale)}}</p>
      <p class="viol-ev">Evidence: ${{ev}}${{v.url?` · in <code>${{esc(v.url)}}</code>`:""}}</p>
      ${{v.screenshot?`<img class="shot" src="${{v.screenshot}}" alt="state where the violation was found">`:""}}</div>`;
  }}).join("");
  h+=`</div>`;
  h+=`<div class="panel"><span class="eyebrow">Exploration graph</span><p class="note">Nodes = pages, edges = actions the crawler took. Dotted = back-edge (navigation loop). Blue = seed page, red = a page with a violation.</p><div id="graphbox" style="overflow-x:auto">building…</div></div>`;
  if(r.pages&&r.pages.length) h+=`<div class="panel"><span class="eyebrow">Pages explored (${{r.pages.length}})</span><div class="pages">`+
    r.pages.map(p=>`<div class="pg">${{p.screenshot?`<img src="${{p.screenshot}}" alt="">`:""}}<span>${{esc(p.url)}}</span></div>`).join("")+`</div></div>`;
  out.innerHTML=h;
  drawGraph(r);
}}

function _mmShort(u){{ const b=String(u).split("/").pop()||String(u); return b.length>28?b.slice(0,26)+"…":b; }}
function mermaidText(r){{
  const seen=new Map();
  const id=u=>{{ if(!seen.has(u)) seen.set(u,"n"+seen.size); return seen.get(u); }};
  const L=["flowchart TD","  classDef seed fill:#1f6feb,stroke:#1f6feb,color:#fff","  classDef viol fill:#fbeae8,stroke:#c5322a,color:#c5322a"];
  (r.pages||[]).forEach(p=>{{ L.push(`  ${{id(p.url)}}["${{_mmShort(p.url).replace(/"/g,"'")}}"]`); }});
  (r.graph_edges||[]).forEach(e=>{{
    const a=id(e.from), b=id(e.to), lbl=(e.label||"").replace(/"/g,"'").slice(0,24);
    L.push(e.back ? `  ${{a}} -. "${{lbl}} (loop)" .-> ${{b}}` : `  ${{a}} -- "${{lbl}}" --> ${{b}}`);
  }});
  const viol=[...new Set((r.violations||[]).map(v=>v.url).filter(Boolean).map(id))];
  if(r.seed && seen.has(r.seed)) L.push(`  class ${{id(r.seed)}} seed`);
  if(viol.length) L.push(`  class ${{viol.join(",")}} viol`);
  return L.join("\\n");
}}
async function drawGraph(r){{
  const box=document.querySelector("#graphbox"); if(!box) return;
  if(!(r.graph_edges&&r.graph_edges.length)){{ box.innerHTML='<p class="note">Single state — no navigation edges to graph.</p>'; return; }}
  if(!window._mermaid){{ box.innerHTML='<p class="note">graph library still loading — run again</p>'; return; }}
  try{{
    const dark=matchMedia("(prefers-color-scheme: dark)").matches;
    window._mermaid.initialize({{startOnLoad:false,theme:dark?"dark":"neutral",flowchart:{{curve:"basis"}},securityLevel:"strict"}});
    const {{svg}}=await window._mermaid.render("expg"+Date.now(), mermaidText(r));
    box.innerHTML=svg;
  }}catch(err){{ box.innerHTML='<p class="err">graph render failed: '+esc(String(err))+'</p>'; }}
}}
</script></body></html>
"""
