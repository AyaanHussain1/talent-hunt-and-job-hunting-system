/* TalentAI SPA — vanilla JS frontend for the FastAPI backend. No build step. */
(function () {
  "use strict";

  var LS_CAND = "talentai_active_candidate";

  var state = {
    apiUrl: location.protocol === "file:" ? "http://127.0.0.1:8000" : location.origin,
    activeId: parseInt(localStorage.getItem(LS_CAND) || "", 10) || null,
    candidates: [],
    jobs: [],
    lastMatches: {},
  };

  var view = document.getElementById("view");
  var crumb = document.getElementById("crumb");
  var candPill = document.getElementById("candPill");
  var toasts = document.getElementById("toasts");

  var TITLES = {
    dashboard: ["Dashboard", "Live platform metrics and overview"],
    candidates: ["Candidate Management", "Register talent and inspect full profiles"],
    resume: ["Resume & ATS", "Upload PDF resumes and generate ATS reports"],
    github: ["GitHub Analyzer", "Save and inspect developer activity"],
    portfolio: ["Portfolio Scoring", "Score project quality and readiness"],
    matching: ["Job Matching", "Vector + keyword fusion recommendations"],
    jobs: ["Job Listings", "Create postings and manage open roles"],
    employer: ["Employer Portal", "Search talent and rank per role"],
  };

  /* ---------------- utils ---------------- */
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function toast(msg, type) {
    var el = document.createElement("div");
    el.className = "toast " + (type || "");
    el.textContent = msg;
    toasts.appendChild(el);
    setTimeout(function () { el.style.opacity = "0"; setTimeout(function(){ el.remove(); }, 300); }, 4200);
  }
  function base() { return state.apiUrl.replace(/\/+$/, ""); }
  function setActive(id) {
    state.activeId = id || null;
    if (id) localStorage.setItem(LS_CAND, String(id)); else localStorage.removeItem(LS_CAND);
    renderPill();
  }
  function renderPill() {
    if (state.activeId) {
      var c = state.candidates.find(function (x) { return x.id === state.activeId; });
      candPill.textContent = "● #" + state.activeId + (c ? " · " + c.full_name : "");
      candPill.classList.remove("empty");
    } else { candPill.textContent = "No candidate"; candPill.classList.add("empty"); }
  }
  function parseMaybe(v) {
    if (typeof v === "string") { try { return JSON.parse(v); } catch (e) { return v; } }
    return v;
  }
  function asList(v) { v = parseMaybe(v); return Array.isArray(v) ? v : (v ? [v] : []); }
  function fmtDate(s) { return s ? String(s).slice(0, 10) : "—"; }
  function githubUsername(v) {
    v = (v || "").trim().replace(/\/+$/, "");
    if (/github\.com/i.test(v)) {
      var path = v.replace(/^https?:\/\//i, "").split("/");
      var idx = path.findIndex(function (p) { return p.toLowerCase() === "github.com"; });
      var user = idx >= 0 ? path[idx + 1] : path[0];
      return (user || "").replace(/^@/, "");
    }
    return v.replace(/^@/, "");
  }
  function barClass(s) { s = Number(s); if (s >= 70) return "good"; if (s >= 40) return "warn"; return "bad"; }

  /* ---------------- api ---------------- */
  async function req(method, path, opts) {
    opts = opts || {};
    var url = base() + path;
    if (opts.params) {
      var q = new URLSearchParams();
      Object.keys(opts.params).forEach(function (k) {
        if (opts.params[k] != null && opts.params[k] !== "") q.append(k, opts.params[k]);
      });
      var qs = q.toString();
      if (qs) url += "?" + qs;
    }
    var cfg = { method: method, headers: {} };
    if (opts.body !== undefined) { cfg.headers["Content-Type"] = "application/json"; cfg.body = JSON.stringify(opts.body); }
    if (opts.file) { cfg.body = opts.file; } // FormData: let browser set content-type
    var ctrl = new AbortController();
    var t = setTimeout(function () { ctrl.abort(); }, opts.timeout || 60000);
    try {
      var res = await fetch(url, Object.assign(cfg, { signal: ctrl.signal }));
      var text = await res.text();
      var data = null;
      try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
      if (!res.ok) {
        var detail = (data && data.detail) || text || ("HTTP " + res.status);
        throw new Error(typeof detail === "string" ? detail.slice(0, 400) : ("HTTP " + res.status));
      }
      return data;
    } finally { clearTimeout(t); }
  }
  var apiGet = function (p, o) { return req("GET", p, o); };
  var apiPost = function (p, o) { return req("POST", p, o); };

  async function checkHealth() {
    try {
      await req("GET", "/health", { timeout: 8000 });
      return true;
    } catch (e) {
      try {
        await req("GET", "/candidates/", { timeout: 8000 });
        return true;
      } catch (e2) {
        return false;
      }
    }
  }
  async function refreshCache() {
    try { var c = await apiGet("/candidates/"); state.candidates = Array.isArray(c) ? c : []; }
    catch (e) { state.candidates = []; }
    try { var j = await apiGet("/jobs/"); state.jobs = Array.isArray(j) ? j : []; }
    catch (e2) { state.jobs = []; }
    renderPill();
  }

  /* ---------------- shared html ---------------- */
  function hero(title, sub) {
    return '<section class="hero"><span class="badge">AI-Powered Hiring</span><h1>' + esc(title) + '</h1><p>' + esc(sub) + '</p></section>';
  }
  function metricCard(label, value) {
    return '<div class="card metric"><div class="v">' + esc(value) + '</div><div class="l">' + esc(label) + '</div></div>';
  }
  function tags(list, cls) {
    list = asList(list).filter(Boolean);
    if (!list.length) return '<p class="muted small">—</p>';
    return '<div class="tags">' + list.slice(0, 14).map(function (s) {
      return '<span class="tag ' + (cls || "") + '">' + esc(typeof s === "object" ? JSON.stringify(s) : s) + '</span>';
    }).join("") + (list.length > 14 ? '<span class="tag amber">+' + (list.length - 14) + ' more</span>' : '') + '</div>';
  }
  function scoreBar(label, score, max) {
    max = max || 100;
    score = Math.max(0, Math.min(max, Number(score) || 0));
    var pct = Math.round((score / max) * 100);
    return '<div class="score"><div class="top"><span>' + esc(label) + '</span><span>' + score + '/' + max + '</span></div>' +
      '<div class="bar ' + barClass(pct) + '"><i style="width:' + pct + '%"></i></div></div>';
  }
  function ctxBar(extra) {
    var c = state.candidates.find(function (x) { return x.id === state.activeId; });
    var who = c ? "#" + c.id + " · " + esc(c.full_name) : (state.activeId ? "#" + state.activeId : "none selected");
    return '<div class="ctx"><span class="who">Active candidate: ' + who + '</span>' +
      '<span class="row"><button class="btn btn-sm" data-act="pick">Change</button>' +
      (extra || "") + '</span></div>';
  }
  function tableHtml(cols, rows) {
    if (!rows.length) return '<div class="empty"><div class="big">∅</div><p>No records found.</p></div>';
    return '<div class="tbl-wrap"><table class="tbl"><thead><tr>' +
      cols.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join("") + '</tr></thead><tbody>' +
      rows.map(function (r) {
        return '<tr>' + r.map(function (cell) { return '<td>' + cell + '</td>'; }).join("") + '</tr>';
      }).join("") + '</tbody></table></div>';
  }
  function spinnerBtn(btn, on, label) {
    if (on) { btn.dataset.orig = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>' + esc(label || "Working…"); }
    else { btn.disabled = false; if (btn.dataset.orig) btn.innerHTML = btn.dataset.orig; }
  }

  /* ---------------- candidate picker modal ---------------- */
  var overlay = document.getElementById("overlay");
  function openPicker() {
    document.getElementById("candSearch").value = "";
    drawPicker("");
    overlay.hidden = false;
  }
  function drawPicker(q) {
    q = (q || "").toLowerCase();
    var list = document.getElementById("candList");
    var items = state.candidates.filter(function (c) {
      return !q || (c.full_name + " " + (c.email || "") + " " + c.id).toLowerCase().includes(q);
    });
    list.innerHTML = items.length ? items.map(function (c) {
      return '<div class="cand-item" data-id="' + c.id + '"><div><b>' + esc(c.full_name) + ' <span class="mono">#' + c.id + '</span></b>' +
        '<span>' + esc(c.email || "no email") + '</span></div><button class="btn btn-sm btn-primary">Use</button></div>';
    }).join("") : '<div class="empty">No candidates match.</div>';
    list.querySelectorAll(".cand-item").forEach(function (el) {
      el.addEventListener("click", function () {
        setActive(parseInt(el.dataset.id, 10));
        overlay.hidden = true;
        toast("Active candidate set to #" + el.dataset.id, "ok");
        rerender();
      });
    });
  }

  /* ---------------- ROUTER ---------------- */
  var routes = {};
  function navigate() {
    var h = (location.hash || "#/dashboard").replace("#/", "");
    var name = h.split("?")[0] || "dashboard";
    if (!routes[name]) name = "dashboard";
    document.querySelectorAll(".side-link").forEach(function (a) {
      a.classList.toggle("active", a.dataset.route === name);
    });
    var t = TITLES[name] || [name, ""];
    crumb.innerHTML = "<strong>" + esc(t[0]) + "</strong><span>" + esc(t[1]) + "</span>";
    document.body.classList.remove("menu-open");
    routes[name]();
    window.scrollTo(0, 0);
  }
  function rerender() { navigate(); }
  function bindCtx(root) {
    var b = root.querySelector('[data-act="pick"]');
    if (b) b.addEventListener("click", openPicker);
  }

  /* ================= DASHBOARD ================= */
  routes.dashboard = async function () {
    view.innerHTML = hero("TalentAI Platform", "Discover top engineering talent with resume parsing, GitHub analysis, portfolio scoring, and intelligent job matching — all in one place.") +
      '<div class="grid g4" id="mrow">' + metricCard("Total Candidates", "…") + metricCard("Open Positions", "…") +
      metricCard("Active Candidate", state.activeId || "None") + metricCard("API Status", "…") + '</div>' +
      '<h2 class="section-title">Platform Modules</h2><div class="grid g4" id="mods"></div>' +
      '<h2 class="section-title">Recent Candidates</h2><div id="rc"></div>' +
      '<h2 class="section-title">Latest Job Postings</h2><div id="rj"></div>';
    var mods = [
      ["Dashboard", "Real-time platform metrics and overview.", "dashboard"],
      ["Candidates", "Register talent and inspect full profiles.", "candidates"],
      ["Resume & ATS", "Upload PDFs and get ATS optimization reports.", "resume"],
      ["GitHub", "Extract repos, languages, and dev activity.", "github"],
      ["Portfolio", "Score project quality and engineering readiness.", "portfolio"],
      ["Job Matching", "Vector + keyword fusion job recommendations.", "matching"],
      ["Jobs", "Browse all open job postings.", "jobs"],
      ["Employer", "Search by skill and rank candidates per role.", "employer"],
    ];
    document.getElementById("mods").innerHTML = mods.map(function (m) {
      return '<div class="card clickable" data-go="' + m[2] + '"><h3>' + m[0] + '</h3><p>' + m[1] + '</p><p class="small" style="color:var(--cyan);margin-top:8px">Open →</p></div>';
    }).join("");
    view.querySelectorAll("[data-go]").forEach(function (el) {
      el.addEventListener("click", function () { location.hash = "#/" + el.dataset.go; });
    });
    await refreshCache();
    var online = await checkHealth();
    document.getElementById("mrow").innerHTML =
      metricCard("Total Candidates", state.candidates.length) +
      metricCard("Open Positions", state.jobs.length) +
      metricCard("Active Candidate", state.activeId ? "#" + state.activeId : "None") +
      metricCard("API Status", online ? "Online" : "Offline");
    document.getElementById("rc").innerHTML = tableHtml(["ID", "Name", "Email", "Registered"],
      state.candidates.slice(0, 10).map(function (c) {
        return ['<span class="mono">#' + c.id + '</span>', "<b>" + esc(c.full_name) + "</b>", esc(c.email || "—"), esc(fmtDate(c.created_at))];
      }));
    document.getElementById("rj").innerHTML = tableHtml(["ID", "Title", "Company", "Type", "Location"],
      state.jobs.slice(0, 8).map(function (j) {
        return ['<span class="mono">#' + j.id + '</span>', "<b>" + esc(j.title) + "</b>", esc(j.company), esc(j.job_type || "—"), esc(j.location || "—")];
      }));
  };

  /* ================= CANDIDATES ================= */
  routes.candidates = async function () {
    view.innerHTML = hero("Candidate Management", "Register talent, view profiles, and choose the candidate used by analysis pages.") +
      '<div class="tabs"><button class="tab active" data-tab="reg">Register</button>' +
      '<button class="tab" data-tab="prof">Full Profile</button>' +
      '<button class="tab" data-tab="list">All Candidates</button></div><div id="tabBody"></div>';
    var body = document.getElementById("tabBody");
    view.querySelectorAll(".tab").forEach(function (t) {
      t.addEventListener("click", function () {
        view.querySelectorAll(".tab").forEach(function (x) { x.classList.remove("active"); });
        t.classList.add("active");
        draw(t.dataset.tab);
      });
    });
    function draw(which) {
      if (which === "reg") {
        body.innerHTML = '<div class="card"><h3>Create a candidate profile</h3><p>Creates the record every other module attaches to.</p>' +
          '<div class="form-grid" style="margin-top:12px"><div><label class="fl">Full Name *</label><input id="fName" class="input" placeholder="Jane Doe"/></div>' +
          '<div><label class="fl">Email</label><input id="fEmail" class="input" placeholder="jane@example.com"/></div></div>' +
          '<div class="row" style="margin-top:12px"><button class="btn btn-primary" id="createBtn">Create Candidate</button></div><div id="regMsg"></div></div>';
        document.getElementById("createBtn").addEventListener("click", async function (e) {
          var name = document.getElementById("fName").value.trim();
          var email = document.getElementById("fEmail").value.trim();
          if (!name) { toast("Full name is required.", "warn"); return; }
          spinnerBtn(e.target, true, "Creating…");
          try {
            var r = await apiPost("/candidates/", { body: { full_name: name, email: email || null } });
            document.getElementById("regMsg").innerHTML = '<div class="alert ok">Candidate created with ID #' + r.candidate_id + '.</div>';
            setActive(r.candidate_id);
            await refreshCache();
            toast("Candidate #" + r.candidate_id + " created & activated.", "ok");
          } catch (err) { document.getElementById("regMsg").innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
          finally { spinnerBtn(e.target, false); }
        });
      } else if (which === "list") {
        drawList(body);
      } else {
        drawProfile(body);
      }
    }
    async function drawList(el) {
      el.innerHTML = '<div class="card"><div class="spread"><h3 style="margin:0">All candidates</h3><button class="btn btn-sm" id="reloadC">↻ Reload</button></div><div id="ltbl" style="margin-top:12px"></div></div>';
      async function load() {
        await refreshCache();
        var rows = state.candidates.map(function (c) {
          var act = state.activeId === c.id ? '<span class="tag">ACTIVE</span>' : '<button class="btn btn-sm" data-use="' + c.id + '">Activate</button>';
          return ['<span class="mono">#' + c.id + '</span>', "<b>" + esc(c.full_name) + "</b>", esc(c.email || "—"), esc(fmtDate(c.created_at)), act];
        });
        document.getElementById("ltbl").innerHTML = tableHtml(["ID", "Name", "Email", "Created", "Action"], rows);
        el.querySelectorAll("[data-use]").forEach(function (b) {
          b.addEventListener("click", function () { setActive(parseInt(b.dataset.use, 10)); toast("Candidate #" + b.dataset.use + " activated.", "ok"); load(); });
        });
      }
      document.getElementById("reloadC").addEventListener("click", load);
      load();
    }
    async function drawProfile(el) {
      await refreshCache();
      if (!state.candidates.length) { el.innerHTML = '<div class="alert info">No candidates registered yet. Use the Register tab first.</div>'; return; }
      if (!state.activeId) setActive(state.candidates[0].id);
      var opts = state.candidates.map(function (c) {
        return '<option value="' + c.id + '"' + (c.id === state.activeId ? " selected" : "") + '>' + esc(c.full_name) + ' (#' + c.id + ')</option>';
      }).join("");
      el.innerHTML = '<div class="card"><div class="row"><select id="profSel" class="input" style="max-width:340px">' + opts + '</select>' +
        '<button class="btn btn-primary btn-sm" id="profGo">Activate</button>' +
        '<span class="row" style="margin-left:auto"><button class="btn btn-sm" data-nav="resume">Resume →</button><button class="btn btn-sm" data-nav="github">GitHub →</button><button class="btn btn-sm" data-nav="portfolio">Portfolio →</button><button class="btn btn-sm" data-nav="matching">Matching →</button></span></div>' +
        '<div id="profBody" style="margin-top:14px"></div></div>';
      el.querySelectorAll("[data-nav]").forEach(function (b) {
        b.addEventListener("click", function () { location.hash = "#/" + b.dataset.nav; });
      });
      document.getElementById("profGo").addEventListener("click", function () {
        setActive(parseInt(document.getElementById("profSel").value, 10));
        loadProf();
      });
      async function loadProf() {
        var pb = document.getElementById("profBody");
        pb.innerHTML = '<div class="alert info"><span class="spin"></span>Loading profile…</div>';
        try {
          var d = await apiGet("/candidates/" + state.activeId);
          var cand = d.candidate || {}, resume = d.resume || null, gh = d.github || null, pf = d.portfolio || null;
          var pfScore = (pf && Number(pf.total_repos) > 0 && pf.portfolio_score != null) ? Number(pf.portfolio_score).toFixed(1) + " / 100" : "Not available";
          var h = '<div class="kv"><div class="card"><div class="k">Candidate</div><div class="val">' + esc(cand.full_name || "—") + '</div></div>' +
            '<div class="card"><div class="k">Email</div><div class="val" style="font-size:.9rem">' + esc(cand.email || "—") + '</div></div>' +
            '<div class="card"><div class="k">Portfolio Score</div><div class="val">' + esc(pfScore) + '</div></div></div>';
          if (resume) {
            h += '<h4>Resume</h4>' + tags(resume.skills, "blue");
            [["Education", "education"], ["Projects", "projects"], ["Experience", "experience"]].forEach(function (pair) {
              var items = asList(resume[pair[1]]);
              if (items.length) {
                h += '<details class="acc"><summary>' + pair[0] + ' (' + items.length + ')</summary><div class="body"><pre style="white-space:pre-wrap;font-size:.78rem">' + esc(JSON.stringify(items, null, 2)).slice(0, 4000) + '</pre></div></details>';
              }
            });
          }
          if (gh) {
            h += '<h4>GitHub</h4><div class="grid g3"><div class="card"><div class="k fld-label">Username</div><div class="val">' + esc(gh.github_username || "—") + '</div></div>' +
              '<div class="card"><div class="k fld-label">Public repos</div><div class="val">' + esc(gh.public_repos) + '</div></div>' +
              '<div class="card"><div class="k fld-label">Followers</div><div class="val">' + esc(gh.followers) + '</div></div></div>';
          }
          if (pf) {
            h += '<h4>Portfolio</h4><div class="grid g2"><div class="card"><b>Strengths</b><ul class="list-clean">' +
              asList(pf.strengths).map(function (s) { return '<li>' + esc(s) + '</li>'; }).join("") + '</ul></div>' +
              '<div class="card"><b>Areas to improve</b><ul class="list-clean">' +
              asList(pf.weaknesses).map(function (s) { return '<li>' + esc(s) + '</li>'; }).join("") + '</ul></div></div>';
          }
          if (!resume && !gh && !pf) h += '<div class="alert info">No resume, GitHub, or portfolio data yet for this candidate.</div>';
          pb.innerHTML = h;
        } catch (err) { pb.innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
      }
      loadProf();
    }
    draw("reg");
  };

  /* ================= RESUME & ATS ================= */
  routes.resume = async function () {
    await refreshCache();
    view.innerHTML = hero("Resume & ATS", "Upload PDF resumes and generate ATS optimization reports.") +
      '<div id="ctx"></div><div class="card"><h3>Upload Resume</h3><p>PDF only. Uploading replaces the stored resume for the active candidate.</p>' +
      '<div class="drop" id="drop" style="margin-top:12px"><div style="font-size:2rem">📄</div><p><b>Drop a PDF here or click to browse</b></p><p class="small muted" id="fileName">No file selected</p><input type="file" id="fileInp" accept="application/pdf"/></div>' +
      '<div class="row" style="margin-top:12px"><button class="btn btn-primary" id="upBtn" disabled>Upload & Parse Resume</button></div><div id="upMsg"></div></div>' +
      '<h2 class="section-title">ATS Diagnostic Report</h2><div class="card"><div class="row"><button class="btn btn-primary" id="atsBtn">Generate ATS Report</button></div><div id="atsOut" style="margin-top:12px"><p class="muted">Run the report against the stored resume.</p></div></div>';
    var ctx = document.getElementById("ctx");
    if (!state.activeId) {
      ctx.innerHTML = '<div class="alert warn">Select an active candidate to continue. <button class="btn btn-sm btn-primary" data-act="pick">Select candidate</button></div>';
      bindCtx(view);
      document.getElementById("upBtn").disabled = true;
      document.getElementById("atsBtn").disabled = true;
      return;
    }
    ctx.innerHTML = ctxBar(); bindCtx(view);
    var file = null;
    var drop = document.getElementById("drop"), fi = document.getElementById("fileInp");
    drop.addEventListener("click", function () { fi.click(); });
    fi.addEventListener("change", function () {
      file = fi.files[0] || null;
      document.getElementById("fileName").textContent = file ? file.name + " (" + Math.round(file.size / 1024) + " KB)" : "No file selected";
      document.getElementById("upBtn").disabled = !file;
    });
    document.getElementById("upBtn").addEventListener("click", async function (e) {
      if (!file) return;
      spinnerBtn(e.target, true, "Parsing with LLM…");
      try {
        var fd = new FormData(); fd.append("file", file, file.name);
        var r = await apiPost("/candidates/" + state.activeId + "/resume", { file: fd, timeout: 180000 });
        document.getElementById("upMsg").innerHTML = '<div class="alert ok">Resume parsed and saved.</div>' +
          '<div class="grid g3" style="margin-top:10px">' + metricCard("Skills Found", r.skills_found || 0) + metricCard("Projects Found", r.projects_found || 0) + metricCard("Education Found", r.education_found || 0) + '</div>';
        toast("Resume parsed & saved.", "ok");
      } catch (err) { document.getElementById("upMsg").innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
      finally { spinnerBtn(e.target, false); }
    });
    document.getElementById("atsBtn").addEventListener("click", async function (e) {
      var out = document.getElementById("atsOut");
      spinnerBtn(e.target, true, "Analyzing…");
      out.innerHTML = '<div class="alert info"><span class="spin"></span>Analyzing resume for ATS compatibility…</div>';
      try {
        var r = await apiGet("/candidates/" + state.activeId + "/ats", { timeout: 90000 });
        var fields = [["Contact", "contact_score"], ["Summary", "summary_score"], ["Skills", "skills_score"], ["Experience", "experience_score"], ["Education", "education_score"], ["Projects", "projects_score"], ["Certifications", "certifications_score"], ["Formatting", "formatting_score"]];
        var h = '<div class="spread"><h3 style="margin:0">Overall ATS Score: <span class="pill-score">' + esc(r.overall_score || 0) + '/100</span></h3></div>' +
          '<p class="muted small">Section points add up to the overall score.</p>' +
          '<div class="score-grid" style="margin-top:10px">' + fields.map(function (f) {
            var max = (r.category_maxima && r.category_maxima[f[1]]) || 0;
            return scoreBar(f[0], r[f[1]] || 0, max || 100);
          }).join("") + '</div>';
        if (r.hiring_recommendation) h += '<div class="alert info" style="margin-top:12px"><b>Hiring recommendation:</b> ' + esc(r.hiring_recommendation) + '</div>';
        var st = asList(r.strengths), wk = asList(r.weaknesses);
        if (st.length) h += '<h4>Strengths</h4><ul class="list-clean">' + st.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join("") + '</ul>';
        if (wk.length) h += '<h4>Areas to Improve</h4><ul class="list-clean">' + wk.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join("") + '</ul>';
        if (r.suggestions && r.suggestions.length) h += '<details class="acc"><summary>Detailed Suggestions (' + r.suggestions.length + ')</summary><div class="body"><ul class="list-clean">' + r.suggestions.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join("") + '</ul></div></details>';
        if (r.missing_keywords && r.missing_keywords.length) h += '<h4>Missing Keywords</h4>' + tags(r.missing_keywords, "amber");
        out.innerHTML = h;
      } catch (err) { out.innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
      finally { spinnerBtn(e.target, false); }
    });
  };

  /* ================= GITHUB ================= */
  routes.github = async function () {
    await refreshCache();
    view.innerHTML = hero("GitHub Analyzer", "Use an existing GitHub profile or save a new one for the selected candidate.") + '<div id="ctx"></div><div id="gbody"></div>';
    var ctx = document.getElementById("ctx");
    if (!state.activeId) { ctx.innerHTML = '<div class="alert warn">Select an active candidate first. <button class="btn btn-sm btn-primary" data-act="pick">Select candidate</button></div>'; bindCtx(view); return; }
    ctx.innerHTML = ctxBar(); bindCtx(view);
    var gb = document.getElementById("gbody");
    gb.innerHTML = '<div class="alert info"><span class="spin"></span>Loading GitHub profile…</div>';
    try {
      var d = await apiGet("/candidates/" + state.activeId);
      var gh = d.github || null, resume = d.resume || null;
      var savedUser = (gh && gh.github_username) || githubUsername(resume && resume.github_url ? resume.github_url : "");
      var h = "";
      if (gh) h += '<div class="grid g3">' + metricCard("Saved Account", gh.github_username || "—") + metricCard("Public Repositories", gh.public_repos || 0) + metricCard("Followers", gh.followers || 0) + '</div><div class="alert ok">Saved GitHub data found. Enter another profile only to replace it.</div>';
      else if (savedUser) h += '<div class="alert info">GitHub URL found in stored resume: ' + esc(resume.github_url) + '</div>';
      else h += '<div class="alert warn">No GitHub profile saved. Add a public username or profile URL.</div>';
      h += '<div class="card" style="margin-top:12px"><label class="fl">GitHub username or profile URL</label>' +
        '<div class="row"><input id="ghInp" class="input" style="max-width:420px" placeholder="octocat or https://github.com/octocat" value="' + esc(savedUser || "") + '"/>' +
        '<button class="btn btn-primary" id="ghSave">Save GitHub Data</button></div><div id="ghMsg" style="margin-top:10px"></div></div>';
      gb.innerHTML = h;
      document.getElementById("ghSave").addEventListener("click", async function (e) {
        var u = githubUsername(document.getElementById("ghInp").value);
        if (!u) { toast("Enter a username first.", "warn"); return; }
        spinnerBtn(e.target, true, "Fetching…");
        try {
          var r = await apiPost("/candidates/" + state.activeId + "/github", { params: { github_username: u }, timeout: 120000 });
          document.getElementById("ghMsg").innerHTML = '<div class="alert ok">' + esc(r.message || "Saved.") + ' Repos: ' + (r.repos_saved || 0) + '</div>';
          toast("GitHub data saved.", "ok");
        } catch (err) { document.getElementById("ghMsg").innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
        finally { spinnerBtn(e.target, false); }
      });
    } catch (err) { gb.innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
  };

  /* ================= PORTFOLIO ================= */
  routes.portfolio = async function () {
    await refreshCache();
    view.innerHTML = hero("Portfolio Review", "Check a personal portfolio website for contact details, project evidence, professional links, and basic page structure.") + '<div id="ctx"></div><div id="pbody"></div>';
    var ctx = document.getElementById("ctx");
    if (!state.activeId) { ctx.innerHTML = '<div class="alert warn">Select an active candidate first. <button class="btn btn-sm btn-primary" data-act="pick">Select candidate</button></div>'; bindCtx(view); return; }
    ctx.innerHTML = ctxBar(); bindCtx(view);
    var pb = document.getElementById("pbody");
    pb.innerHTML = '<div class="alert info"><span class="spin"></span>Loading candidate portfolio review…</div>';
    function auditHtml(r) {
      var categories = r.category_scores || {};
      var categoryCards = Object.keys(categories).map(function (name) {
        var category = categories[name];
        return '<div class="card">' + scoreBar(name, category.score, category.max_score) + '</div>';
      }).join("");
      var checks = asList(r.checks).map(function (check) {
        var marker = check.passed ? '<span class="tag green">Found</span>' : '<span class="tag amber">Missing</span>';
        return '<li>' + marker + ' <b>' + esc(check.label) + '</b> <span class="muted">(' +
          esc(check.points) + '/' + esc(check.max_points) + ' pts)</span>' +
          (check.detail ? '<div class="muted small">' + esc(check.detail) + '</div>' : '') + '</li>';
      }).join("");
      return '<div class="card" style="margin-top:12px"><div class="spread"><h3 style="margin:0">Portfolio audit</h3>' +
        '<a href="' + esc(r.portfolio_url) + '" target="_blank" rel="noopener noreferrer">Open portfolio ↗</a></div>' +
        '<div style="max-width:420px;margin-top:14px">' + scoreBar("Overall portfolio completeness", r.overall_score, 100) + '</div>' +
        '<div class="grid g3" style="margin-top:12px">' + categoryCards + '</div>' +
        '<h4>Review checklist</h4><ul class="list-clean">' + checks + '</ul>' +
        '<p class="muted small">This score checks visible page content and links; it does not judge design quality, accessibility compliance, or job fit.</p></div>';
    }
    try {
      var d = await apiGet("/candidates/" + state.activeId);
      var savedAudit = d.portfolio_audit || null;
      pb.innerHTML = '<div class="card"><h3>Does this candidate have a portfolio website?</h3>' +
        '<p>Enter a public website link to check identity/contact details, project examples, project details, professional links, and page basics.</p>' +
        '<div class="row" style="margin-top:12px"><button class="btn btn-primary" id="hasPortfolio">Yes, review portfolio link</button>' +
        '<button class="btn" id="skipPortfolio">No portfolio — continue</button></div></div><div id="portfolioReview"></div>';
      var review = document.getElementById("portfolioReview");
      document.getElementById("skipPortfolio").addEventListener("click", function () {
        review.innerHTML = '<div class="alert info">Portfolio review skipped. Continue with <a href="#/resume">Resume &amp; ATS</a> or <a href="#/matching">Job Matching</a>.</div>';
      });
      document.getElementById("hasPortfolio").addEventListener("click", function () {
        review.innerHTML = '<div class="card" style="margin-top:12px"><label class="fl" for="portfolioUrl">Portfolio website URL</label>' +
          '<div class="row"><input id="portfolioUrl" class="input" style="max-width:520px" type="url" placeholder="https://example.com" value="' +
          esc((savedAudit && savedAudit.portfolio_url) || '') + '"/><button class="btn btn-primary" id="auditBtn">' +
          (savedAudit ? "Recheck portfolio" : "Check portfolio") + '</button></div>' +
          '<p class="hint">The page must be publicly reachable without signing in.</p><div id="auditResult"></div></div>';
        var resultEl = document.getElementById("auditResult");
        if (savedAudit) resultEl.innerHTML = auditHtml(savedAudit);
        document.getElementById("auditBtn").addEventListener("click", async function (e) {
          var url = document.getElementById("portfolioUrl").value.trim();
          if (!url) { toast("Enter the portfolio website link.", "warn"); return; }
          spinnerBtn(e.target, true, "Reviewing…");
          try {
            var result = await apiPost("/candidates/" + state.activeId + "/portfolio-site", {
              body: { portfolio_url: url },
              timeout: 30000
            });
            resultEl.innerHTML = auditHtml(result);
            toast("Portfolio review saved.", "ok");
          } catch (err) {
            resultEl.insertAdjacentHTML("afterbegin", '<div class="alert err">' + esc(err.message) + '</div>');
          } finally { spinnerBtn(e.target, false); }
        });
      });
    } catch (err) { pb.innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
  };

  /* ================= JOB MATCHING ================= */
  routes.matching = async function () {
    await refreshCache();
    view.innerHTML = hero("Job Matching", "Two-stage vector + BM25 fusion matching engine.") +
      '<div id="ctx"></div><div class="card"><div class="row"><button class="btn btn-primary" id="runBtn">Run Matching Engine</button>' +
      '<button class="btn" id="loadBtn">Load Saved Matches</button></div><div id="runMsg" style="margin-top:10px"></div></div>' +
      '<h2 class="section-title">Matches</h2><div id="mout"><div class="alert info">Run the engine or load saved matches.</div></div>';
    var ctx = document.getElementById("ctx");
    if (!state.activeId) { ctx.innerHTML = '<div class="alert warn">Select an active candidate first. <button class="btn btn-sm btn-primary" data-act="pick">Select candidate</button></div>'; bindCtx(view); return; }
    ctx.innerHTML = ctxBar(); bindCtx(view);
    function drawMatches(list) {
      var out = document.getElementById("mout");
      if (!list || !list.length) { out.innerHTML = '<div class="alert info">No match records to display.</div>'; return; }
      var rows = list.filter(function (m) { return m && typeof m === "object"; }).map(function (m) {
        var mt = asList(m.matched_skills), ms = asList(m.missing_skills);
        return ['<span class="pill-score">' + (Math.round(Number(m.match_score || 0) * 10) / 10) + '</span>',
          "<b>" + esc(m.title || m.job_title || "—") + "</b>", esc(m.company || "—"), esc(m.job_type || "—"), esc(m.location || "—"),
          esc(mt.join(", ") || "—"), esc(ms.join(", ") || "—")];
      });
      var top = list[0] || {};
      out.innerHTML = tableHtml(["Score", "Title", "Company", "Type", "Location", "Matched", "Missing"], rows) +
        '<div class="grid g2" style="margin-top:12px"><div class="card"><b>Top match — matched skills</b>' + tags(top.matched_skills, "blue") + '</div>' +
        '<div class="card"><b>Skill gaps</b>' + (asList(top.missing_skills).length ? '<ul class="list-clean">' + asList(top.missing_skills).map(function (s) { return '<li>' + esc(s) + '</li>'; }).join("") + '</ul>' : '<p class="muted">No gaps — strong fit.</p>') + '</div></div>';
    }
    document.getElementById("runBtn").addEventListener("click", async function (e) {
      spinnerBtn(e.target, true, "Scoring…");
      try {
        var r = await apiPost("/candidates/" + state.activeId + "/match", { timeout: 180000 });
        document.getElementById("runMsg").innerHTML = '<div class="alert ok">Evaluated <b>' + (r.total_jobs_evaluated || 0) + '</b> jobs for <b>' + esc(r.candidate_name || ("#" + state.activeId)) + '</b>.</div>';
        var m = r.matches || [];
        state.lastMatches[state.activeId] = m;
        drawMatches(m);
        if (!m.length) toast("No matches above threshold.", "warn"); else toast(m.length + " matches computed.", "ok");
      } catch (err) { document.getElementById("runMsg").innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
      finally { spinnerBtn(e.target, false); }
    });
    document.getElementById("loadBtn").addEventListener("click", async function (e) {
      spinnerBtn(e.target, true, "Loading…");
      try {
        var rows = await apiGet("/candidates/" + state.activeId + "/matches");
        state.lastMatches[state.activeId] = Array.isArray(rows) ? rows : [];
        drawMatches(state.lastMatches[state.activeId]);
      } catch (err) { document.getElementById("mout").innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
      finally { spinnerBtn(e.target, false); }
    });
  };

  /* ================= JOBS ================= */
  routes.jobs = async function () {
    view.innerHTML = hero("Job Listings", "Create job postings and manage the roles used for candidate matching.") +
      '<div class="card"><div class="spread"><h3 style="margin:0">Add or update a job</h3><span class="small muted">Same title + company overwrites instead of duplicating</span></div>' +
      '<div class="form-grid" style="margin-top:12px"><div><label class="fl">Job title *</label><input id="jTitle" class="input" placeholder="Backend Developer"/></div>' +
      '<div><label class="fl">Company *</label><input id="jCompany" class="input" placeholder="Example Ltd"/></div>' +
      '<div><label class="fl">Job type</label><select id="jType" class="input"><option>Full-Time</option><option>Remote</option><option>Freelance</option><option>Client</option><option>Internal</option><option>Startup</option></select></div>' +
      '<div><label class="fl">Location</label><input id="jLoc" class="input" placeholder="Karachi or Remote"/></div></div>' +
      '<div style="margin-top:12px"><label class="fl">Required skills (comma separated) *</label><input id="jSkills" class="input" placeholder="Python, FastAPI, SQL, Docker"/></div>' +
      '<div style="margin-top:12px"><label class="fl">Job description</label><textarea id="jDesc" class="input" placeholder="Responsibilities and requirements…"></textarea></div>' +
      '<div class="row" style="margin-top:12px"><button class="btn btn-primary" id="jSave">Save Job</button></div><div id="jMsg"></div></div>' +
      '<h2 class="section-title">All job postings</h2><div class="card"><input id="jFilter" class="input" placeholder="Filter by title, company, location, or skill… (e.g. Python or Remote)" /><div id="jtbl" style="margin-top:12px"></div></div>';
    document.getElementById("jSave").addEventListener("click", async function (e) {
      var title = document.getElementById("jTitle").value.trim();
      var company = document.getElementById("jCompany").value.trim();
      var skills = document.getElementById("jSkills").value.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
      if (!title || !company || !skills.length) { toast("Title, company, and at least one skill are required.", "warn"); return; }
      spinnerBtn(e.target, true, "Saving…");
      try {
        var r = await apiPost("/jobs/", { body: { title: title, company: company, job_type: document.getElementById("jType").value, required_skills: skills, description: document.getElementById("jDesc").value, location: document.getElementById("jLoc").value } });
        document.getElementById("jMsg").innerHTML = '<div class="alert ok">' + esc(r.message || "Job saved.") + '</div>';
        toast("Job saved.", "ok"); loadJobs();
      } catch (err) { document.getElementById("jMsg").innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
      finally { spinnerBtn(e.target, false); }
    });
    async function loadJobs() {
      var wrap = document.getElementById("jtbl");
      wrap.innerHTML = '<div class="alert info"><span class="spin"></span>Loading jobs…</div>';
      try {
        var jobs = await apiGet("/jobs/");
        state.jobs = Array.isArray(jobs) ? jobs : [];
        var q = document.getElementById("jFilter").value.trim().toLowerCase();
        var rows = [];
        state.jobs.forEach(function (j) {
          var skills = asList(j.required_skills);
          var hay = [j.title, j.company, j.location, j.job_type].concat(skills).join(" ").toLowerCase();
          if (q && hay.indexOf(q) === -1) return;
          rows.push(['<span class="mono">#' + j.id + '</span>', "<b>" + esc(j.title) + "</b>", esc(j.company), esc(j.job_type || "—"), esc(j.location || "Not specified"), esc(skills.join(", "))]);
        });
        wrap.innerHTML = rows.length ? tableHtml(["ID", "Title", "Company", "Type", "Location", "Required Skills"], rows) : '<div class="alert info">No jobs match your filter.</div>';
      } catch (err) { wrap.innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
    }
    document.getElementById("jFilter").addEventListener("input", loadJobs);
    loadJobs();
  };

  /* ================= EMPLOYER ================= */
  routes.employer = async function () {
    view.innerHTML = hero("Employer Portal", "Search talent by skill and rank candidates per job.") +
      '<div class="tabs"><button class="tab active" data-tab="s">Skill Search</button><button class="tab" data-tab="r">Rankings by Job</button></div><div id="ebody"></div>';
    var body = document.getElementById("ebody");
    view.querySelectorAll(".tab").forEach(function (t) {
      t.addEventListener("click", function () {
        view.querySelectorAll(".tab").forEach(function (x) { x.classList.remove("active"); });
        t.classList.add("active");
        t.dataset.tab === "s" ? drawSearch() : drawRank();
      });
    });
    function drawSearch() {
      body.innerHTML = '<div class="card"><h3>Find candidates by skill keyword</h3><div class="row" style="margin-top:10px"><input id="skQ" class="input" style="max-width:420px" placeholder="Python, React, Machine Learning…"/>' +
        '<button class="btn btn-primary" id="skGo">Search Talent</button></div><div id="skOut" style="margin-top:12px"><p class="muted">Leave blank to list everyone, ordered by portfolio score.</p></div></div>';
      document.getElementById("skGo").addEventListener("click", async function (e) {
        var out = document.getElementById("skOut");
        spinnerBtn(e.target, true, "Searching…");
        try {
          var q = document.getElementById("skQ").value.trim();
          var rows = await apiGet("/employer/candidates", { params: q ? { skill: q } : {} });
          if (!rows.length) { out.innerHTML = '<div class="alert warn">No candidates matched your query.</div>'; return; }
          out.innerHTML = tableHtml(["ID", "Name", "Email", "Location", "Portfolio", "Skills"],
            rows.map(function (r) {
              var sk = asList(r.skills);
              return ['<span class="mono">#' + r.id + '</span>', "<b>" + esc(r.full_name) + "</b>", esc(r.email || "—"), esc(r.location || "—"),
                r.portfolio_score != null ? '<span class="pill-score">' + Math.round(Number(r.portfolio_score) * 10) / 10 + '</span>' : "—",
                esc(sk.slice(0, 8).join(", ") || "—")];
            })) + '<p class="small muted">' + rows.length + ' candidate(s) found</p>';
        } catch (err) { out.innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
        finally { spinnerBtn(e.target, false); }
      });
    }
    async function drawRank() {
      body.innerHTML = '<div class="card"><h3>Candidate rankings for a specific role</h3><div id="rkCtl" style="margin-top:10px"><span class="spin"></span> Loading jobs…</div><div id="rkOut" style="margin-top:12px"></div></div>';
      try {
        var jobs = await apiGet("/jobs/");
        if (!jobs.length) { document.getElementById("rkCtl").innerHTML = '<div class="alert info">No jobs available.</div>'; return; }
        document.getElementById("rkCtl").innerHTML = '<div class="row"><select id="rkSel" class="input" style="max-width:440px">' +
          jobs.map(function (j) { return '<option value="' + j.id + '">' + esc(j.title) + ' @ ' + esc(j.company || "?") + ' (#' + j.id + ')</option>'; }).join("") +
          '</select><button class="btn btn-primary" id="rkGo">Load Rankings</button></div>';
        document.getElementById("rkGo").addEventListener("click", async function (e) {
          var out = document.getElementById("rkOut");
          spinnerBtn(e.target, true, "Ranking…");
          try {
            var id = document.getElementById("rkSel").value;
            var rk = await apiGet("/employer/jobs/" + id + "/candidates");
            var rows;if (!rk.length) { out.innerHTML = '<div class="alert info">No candidates ranked for this job yet. Run job matching first.</div>'; return; }
            rows = rk.map(function (r, i) {
              return ['<b>#' + (i + 1) + '</b>', "<b>" + esc(r.full_name) + "</b>", esc(r.email || "—"),
                '<span class="pill-score">' + (Math.round(Number(r.match_score || 0) * 10) / 10) + '%</span>',
                r.portfolio_score != null ? String(Math.round(Number(r.portfolio_score) * 10) / 10) : "—",
                esc(asList(r.matched_skills).join(", ") || "—"), esc(asList(r.missing_skills).join(", ") || "—")];
            });
            out.innerHTML = tableHtml(["Rank", "Name", "Email", "Match", "Portfolio", "Matched", "Gaps"], rows) +
              '<div class="alert ok">Top candidate: <b>' + esc(rk[0].full_name) + '</b> — ' + (Math.round(Number(rk[0].match_score || 0) * 10) / 10) + '% match</div>';
          } catch (err) { out.innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
          finally { spinnerBtn(e.target, false); }
        });
      } catch (err) { document.getElementById("rkCtl").innerHTML = '<div class="alert err">' + esc(err.message) + '</div>'; }
    }
    drawSearch();
  };

  /* ---------------- shell wiring ---------------- */
  function initShell() {
    document.getElementById("menuBtn").addEventListener("click", function () { document.body.classList.toggle("menu-open"); });
    document.getElementById("scrim").addEventListener("click", function () { document.body.classList.remove("menu-open"); });
    document.getElementById("refreshBtn").addEventListener("click", async function () { await refreshCache(); rerender(); toast("Refreshed.", "ok"); });
    candPill.addEventListener("click", openPicker);
    document.getElementById("overlayClose").addEventListener("click", function () { overlay.hidden = true; });
    overlay.addEventListener("click", function (e) { if (e.target === overlay) overlay.hidden = true; });
    document.getElementById("candSearch").addEventListener("input", function (e) { drawPicker(e.target.value); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") overlay.hidden = true; });
    window.addEventListener("hashchange", navigate);
  }

  initShell();
  renderPill();
  refreshCache().then(function () { renderPill(); });
  navigate();
})();
