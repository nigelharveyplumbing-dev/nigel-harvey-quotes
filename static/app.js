
let MATERIAL_LIBRARY = __MATERIAL_LIBRARY__;
const FAVOURITE_MATERIALS = __FAVOURITE_MATERIALS__;
const JOB_TEMPLATES = __JOB_TEMPLATES__;

const MATERIAL_ALIAS_RULES = __MATERIAL_ALIAS_RULES__;





async function getSupplierPreference(name) {
  try {
    const res = await fetch(`/api/supplier-preference?q=${encodeURIComponent(name || "")}`);
    if (!res.ok) throw new Error();
    return await res.json();
  } catch (e) {
    return null;
  }
}

async function applySupplierPreferenceToRow(row) {
  const name = row.querySelector(".m-name")?.value || "";
  const supplierSelect = row.querySelector(".m-supplier");
  if (!name || !supplierSelect) return;

  const pref = await getSupplierPreference(name);
  if (pref && pref.preferred_supplier && pref.source === "history") {
    supplierSelect.value = pref.preferred_supplier;
    const note = row.querySelector(".supplier-preference-note");
    if (note) {
      const counts = pref.supplier_counts || {};
      const count = counts[pref.preferred_supplier] || 0;
      note.innerHTML = `Supplier learned from history: ${escapeHtml(pref.preferred_supplier)} used ${count} time(s).`;
    }
  }
}

function updateSupplierPreferenceNotes() {
  document.querySelectorAll("#materials .material-row").forEach(row => {
    applySupplierPreferenceToRow(row);
  });
}

async function loadSupplierPreferencesPanel() {
  const box = document.getElementById("supplierPreferencesPanel");
  if (!box) return;

  try {
    const res = await fetch("/api/supplier-preferences");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not save invoice.");
    const items = data.items || [];

    if (!items.length) {
      box.innerHTML = "No supplier history yet.";
      return;
    }

    box.innerHTML = items.slice(0, 30).map(item => {
      const counts = item.supplier_counts || {};
      const countText = Object.keys(counts).map(k => `${escapeHtml(k)}: ${counts[k]}`).join(" · ");
      const prices = item.average_prices || {};
      const priceText = Object.keys(prices).map(k => `${escapeHtml(k)} avg ${pounds(prices[k])}`).join(" · ");
      return `
        <div class="history-item" style="padding:8px;margin-top:6px;">
          <strong>${escapeHtml(item.material || "Material")}</strong><br>
          Preferred: <strong>${escapeHtml(item.preferred_supplier || "-")}</strong> · Uses: ${item.total_uses || 0}<br>
          <span class="small">${countText}</span><br>
          ${priceText ? `<span class="small">${priceText}</span>` : ""}
        </div>
      `;
    }).join("");
  } catch (e) {
    box.innerHTML = "Could not load supplier preferences.";
  }
}


const FORGOTTEN_ITEM_RULES = [
  {
    trigger: ["outside tap", "hose union bib tap", "wall plate elbow"],
    missing: ["15mm isolating valve", "double check valve 15mm", "pipe clips 15mm", "drain off cock 15mm"],
    job_keywords: ["outside tap", "garden tap", "external tap"],
    reason: "Outside taps usually need isolation, backflow protection, pipe clips and a drain off where freezing is possible."
  },
  {
    trigger: ["trv", "thermostatic radiator valve", "angled trv"],
    missing: ["angled lockshield valve", "radiator valve tail", "ptfe tape", "15mm copper olive", "central heating inhibitor"],
    job_keywords: ["trv", "radiator valve", "heating"],
    reason: "TRV jobs often need a matching lockshield, tails, olives, PTFE and inhibitor if draining/refilling."
  },
  {
    trigger: ["radiator", "radiator replacement"],
    missing: ["angled trv", "angled lockshield valve", "radiator valve tail", "central heating inhibitor", "radiator bleed valve"],
    job_keywords: ["radiator", "rad"],
    reason: "Radiator replacements commonly need valves, tails, inhibitor and bleed parts."
  },
  {
    trigger: ["filling loop", "braided filling loop"],
    missing: ["15mm isolating valve", "double check valve 15mm", "central heating inhibitor"],
    job_keywords: ["filling loop", "pressure", "low pressure", "repressurise"],
    reason: "Filling loop jobs often need isolation/check valve parts and inhibitor if system is topped up/refilled."
  },
  {
    trigger: ["basin waste", "bottle trap", "p trap"],
    missing: ["32mm waste pipe", "32mm waste pipe clips", "32mm solvent weld bend", "silicone"],
    job_keywords: ["basin", "waste", "trap"],
    reason: "Basin waste jobs often need pipe, clips, bends and sealant."
  },
  {
    trigger: ["kitchen sink waste", "sink waste"],
    missing: ["40mm waste pipe", "40mm waste pipe clips", "40mm solvent weld bend", "appliance waste spigot"],
    job_keywords: ["kitchen sink", "sink waste", "waste"],
    reason: "Kitchen sink waste jobs often need 40mm pipe, clips, bends and sometimes appliance spigots."
  },
  {
    trigger: ["tap", "kitchen tap", "basin tap"],
    missing: ["15mm isolating valve", "flexi hose 300mm", "ptfe tape"],
    job_keywords: ["tap", "kitchen tap", "basin tap"],
    reason: "Tap replacements often need isolation valves, flexis and PTFE/sundries."
  },
  {
    trigger: ["toilet", "replace toilet", "toilet replacement"],
    missing: ["straight pan connector", "toilet fixing kit", "15mm isolating valve", "15mm x 1/2 flexi hose", "doughnut washer"],
    job_keywords: ["toilet", "wc"],
    reason: "Toilet jobs often need pan connector, fixings, isolation/flexi and close-coupling seals."
  }
];

function currentMaterialsForForgottenCheck() {
  return [...document.querySelectorAll("#materials .material-row")].map(row => ({
    name: row.querySelector(".m-name")?.value || "",
    quantity: Number(row.querySelector(".m-qty")?.value || 1),
    supplier: row.querySelector(".m-supplier")?.value || "",
    url: row.querySelector(".m-url")?.value || "",
    manual_price: Number(row.querySelector(".m-manual")?.value || 0)
  })).filter(m => m.name.trim());
}

function detectForgottenItemsFrontend() {
  const job = (document.getElementById("job")?.value || "").toLowerCase();
  const materials = currentMaterialsForForgottenCheck();
  const canonicalNames = materials.map(m => canonicalMaterialName(m.name || ""));
  const hay = `${job} ${materials.map(m => m.name).join(" ")} ${canonicalNames.join(" ")}`.toLowerCase();

  const warnings = [];
  const seen = new Set();

  FORGOTTEN_ITEM_RULES.forEach(rule => {
    const triggerHit = (rule.trigger || []).some(t => hay.includes(t)) || (rule.job_keywords || []).some(k => job.includes(k));
    if (!triggerHit) return;

    const missing = [];
    (rule.missing || []).forEach(item => {
      const itemCan = canonicalMaterialName(item);
      const exists = canonicalNames.some(c => itemCan === c || itemCan.includes(c) || c.includes(itemCan));
      if (!exists && !seen.has(itemCan)) {
        seen.add(itemCan);
        missing.push(item);
      }
    });

    if (missing.length) {
      warnings.push({reason: rule.reason, missing});
    }
  });

  return warnings;
}

function addForgottenItem(name) {
  addMaterial({name, quantity: suggestMaterialQuantity(name), supplier: "City Plumbing", manual_price: 0});
  updateForgottenItemWarnings();
  showNotice(`${name} added.`);
}

function updateForgottenItemWarnings() {
  const box = document.getElementById("forgottenItemWarnings");
  if (!box) return;

  const warnings = detectForgottenItemsFrontend();

  if (!warnings.length) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }

  box.style.display = "block";
  box.innerHTML = `
    <strong>Possible forgotten materials</strong><br>
    <span class="small">These are not compulsory, but check them before sending the quote.</span>
    ${warnings.map(w => `
      <div class="history-item" style="margin-top:8px;padding:8px;">
        <strong>${escapeHtml(w.reason || "Check missing items")}</strong><br>
        ${(w.missing || []).map(item => `
          <div style="display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;margin-top:6px;">
            <span>• ${escapeHtml(item)}</span>
            <button type="button" class="btn-light" onclick='addForgottenItem(${JSON.stringify(item)})'>Add</button>
          </div>
        `).join("")}
      </div>
    `).join("")}
  `;
}


const SMART_QUANTITY_RULES = [
  {match: ["pipe clips 15mm", "15mm pipe clips"], default_quantity: 6, job_keywords: ["outside tap", "fridge", "pipe run"]},
  {match: ["32mm waste pipe clips", "waste pipe clips 32"], default_quantity: 4, job_keywords: ["basin", "waste"]},
  {match: ["40mm waste pipe clips", "waste pipe clips 40"], default_quantity: 4, job_keywords: ["sink", "shower", "waste"]},
  {match: ["15mm copper pipe"], default_quantity: 1, job_keywords: ["small", "tap", "fridge", "outside tap"]},
  {match: ["15mm endfeed elbow", "endfeed elbow"], default_quantity: 4, job_keywords: ["outside tap", "pipe run", "leak"]},
  {match: ["15mm endfeed tee", "endfeed tee"], default_quantity: 1, job_keywords: ["outside tap", "branch"]},
  {match: ["15mm compression coupler", "compression coupler"], default_quantity: 2, job_keywords: ["repair", "leak", "extension"]},
  {match: ["15mm isolating valve", "isolating valve"], default_quantity: 1, job_keywords: ["fridge", "appliance"]},
  {match: ["15mm isolating valve", "isolating valve"], default_quantity: 2, job_keywords: ["tap", "basin tap", "kitchen tap"]},
  {match: ["flexi hose 300mm", "flexi hose 500mm", "flexible tap connector"], default_quantity: 2, job_keywords: ["tap", "basin", "kitchen"]},
  {match: ["15mm copper olive", "olive"], default_quantity: 2, job_keywords: ["trv", "valve", "compression"]},
  {match: ["radiator valve tail", "radiator tail"], default_quantity: 2, job_keywords: ["radiator", "trv"]},
  {match: ["angled trv", "thermostatic radiator valve"], default_quantity: 1, job_keywords: ["trv", "radiator"]},
  {match: ["angled lockshield valve", "lockshield"], default_quantity: 1, job_keywords: ["trv", "radiator"]},
  {match: ["ptfe tape"], default_quantity: 1, job_keywords: ["any"]},
  {match: ["silicone"], default_quantity: 1, job_keywords: ["bath", "basin", "toilet", "sink"]}
];

function learnedQuantityFromCurrentJob(name) {
  if (!LAST_LEARNING_DATA || !LAST_LEARNING_DATA.common_materials) return null;

  const canonical = canonicalMaterialName(name || "");
  const match = (LAST_LEARNING_DATA.common_materials || []).find(m => canonicalMaterialName(m.name || "") === canonical);

  if (!match) return null;

  const avgQty = Number(match.average_quantity || 0);
  const usedCount = Number(match.used_count || 0);

  if (avgQty > 0 && usedCount >= 1) {
    return {
      quantity: Math.max(1, Math.round(avgQty)),
      average_quantity: avgQty,
      used_count: usedCount,
      used_percent: Number(match.used_percent || 0),
      source: "learned"
    };
  }

  return null;
}

function ruleQuantitySuggestion(name, jobText = "") {
  const canonical = canonicalMaterialName(name || "");
  const hay = `${canonical} ${name || ""}`.toLowerCase();
  const job = (jobText || document.getElementById("job")?.value || "").toLowerCase();

  let best = null;
  let bestScore = -1;

  SMART_QUANTITY_RULES.forEach(rule => {
    if (!(rule.match || []).some(term => hay.includes(term))) return;

    let score = 1;
    const kws = rule.job_keywords || [];
    if (kws.includes("any")) score += 1;
    kws.forEach(kw => {
      if (kw && kw !== "any" && job.includes(kw)) score += 3;
    });

    if (score > bestScore) {
      best = rule;
      bestScore = score;
    }
  });

  return best ? Number(best.default_quantity || 1) : 1;
}

function suggestMaterialQuantityInfo(name, jobText = "") {
  const learned = learnedQuantityFromCurrentJob(name);
  if (learned) return learned;

  return {
    quantity: ruleQuantitySuggestion(name, jobText),
    average_quantity: null,
    used_count: 0,
    used_percent: 0,
    source: "rule"
  };
}

function suggestMaterialQuantity(name, jobText = "") {
  return Number(suggestMaterialQuantityInfo(name, jobText).quantity || 1);
}

function applySmartQuantityToMaterial(material) {
  const out = {...material};
  const hasExplicitQty = out.quantity !== undefined && out.quantity !== null && String(out.quantity).trim() !== "";
  if (!hasExplicitQty || Number(out.quantity) === 1) {
    const info = suggestMaterialQuantityInfo(out.name || "");
    const suggested = Number(info.quantity || 1);
    if (suggested && suggested > 1) out.quantity = suggested;
    out.quantity_source = info.source;
    out.learned_average_quantity = info.average_quantity;
    out.learned_used_count = info.used_count;
  }
  return out;
}


const MATERIAL_CHARGING_RULES = {
  "ptfe tape": {
    material_type: "consumable",
    charge_method: "partial",
    default_charge: 0.50,
    customer_label: "Small consumable allowance",
    note: "Partial use only. Do not charge whole roll unless specifically supplied."
  },
  "silicone": {
    material_type: "consumable",
    charge_method: "partial",
    default_charge: 3.00,
    customer_label: "Sealant allowance",
    note: "Partial tube use unless full tube supplied."
  },
  "solvent weld cement": {
    material_type: "consumable",
    charge_method: "partial",
    default_charge: 2.00,
    customer_label: "Solvent cement allowance",
    note: "Partial use only."
  },
  "central heating inhibitor": {
    material_type: "chargeable",
    charge_method: "full",
    default_charge: null,
    customer_label: "Central heating inhibitor",
    note: "Normally charged as full bottle when used."
  },
  "15mm copper olive": {
    material_type: "small_part",
    charge_method: "small_part",
    default_charge: 0.30,
    customer_label: "Compression olives",
    note: "Small fittings normally charged individually or absorbed into sundries."
  }
};

function getMaterialChargingRule(name) {
  const canonical = canonicalMaterialName(name);
  return MATERIAL_CHARGING_RULES[canonical] || {
    material_type: "chargeable",
    charge_method: "full",
    default_charge: null,
    customer_label: canonical,
    note: "Full chargeable material."
  };
}

function applyChargingRuleToMaterial(material) {
  const rule = getMaterialChargingRule(material.name || "");
  const out = {...material};
  out.material_type = rule.material_type;
  out.charge_method = rule.charge_method;
  out.customer_label = rule.customer_label;
  out.charge_note = rule.note;

  // Keep the full product/manual price for memory.
  // Use a separate quote charge for partial consumables.
  if ((rule.charge_method === "partial" || rule.charge_method === "small_part") && Number(rule.default_charge || 0) > 0) {
    out.quote_charge_override = Number(rule.default_charge);
  }

  return out;
}


function cleanMaterialNameForMatching(name) {
  return (name || "")
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/(\d+)\s*mm\b/g, "$1mm")
    .replace(/\bend[\s-]?feed\b/g, "endfeed")
    .replace(/\b90\s*(?:degree|degrees|deg)\b/g, " ")
    .replace(/\b(plumbright|plumbfix|regin|kudox|stelrad|city plumbing|screwfix|toolstation|selco|topps tiles)\b/g, " ")
    .replace(/\b(white|chrome plated|chrome|copper|each|single|individual|pack of|pack)\b/g, " ")
    .replace(/\b(fitting|fittings|connector|connectors)\b/g, " ")
    .replace(/[^a-z0-9/.\- ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function materialMatchTokens(name) {
  const cleaned = cleanMaterialNameForMatching(name);
  const stop = new Set(["the", "and", "for", "with", "type", "degree", "degrees"]);
  return cleaned
    .split(/\s+/)
    .filter(Boolean)
    .filter(token => !stop.has(token));
}

function materialDimensions(name) {
  const cleaned = String(name || "").toLowerCase().replace(/\s+/g, " ");
  const sizes = [...cleaned.matchAll(/\b(\d{1,4})\s*mm\b/g)].map(match => Number(match[1]));
  return [...new Set(sizes)].sort((a, b) => a - b);
}

function materialFamily(name) {
  const cleaned = cleanMaterialNameForMatching(name);
  if (/\breducing tee\b|\btee\b/.test(cleaned)) return "tee";
  if (/\belbow\b|\bbend\b/.test(cleaned)) return "elbow";
  if (/\bcoupler\b|\bcoupling\b/.test(cleaned)) return "coupler";
  if (/\bcopper pipe\b|\bpipe 3m\b/.test(cleaned)) return "pipe";
  if (/\bradiator valve set\b/.test(cleaned)) return "radiator valve set";
  if (/\btrv\b|\bthermostatic radiator valve\b/.test(cleaned)) return "trv";
  if (/\blockshield\b/.test(cleaned)) return "lockshield";
  if (/\binhibitor\b/.test(cleaned)) return "inhibitor";
  if (/\bptfe\b/.test(cleaned)) return "ptfe";
  if (/\bradiator\b/.test(cleaned)) return "radiator";
  return "";
}

function savedMaterialPrice(item) {
  return Number(
    item?.last_live_price ||
    item?.last_price ||
    item?.last_manual_price ||
    item?.default_price ||
    0
  );
}

function scoreSavedMaterialMatch(requestedName, candidate) {
  const requestedTokens = materialMatchTokens(requestedName);
  const candidateTokens = materialMatchTokens(candidate?.name || "");
  if (!requestedTokens.length || !candidateTokens.length) return 0;

  const requestedFamily = materialFamily(requestedName);
  const candidateFamily = materialFamily(candidate?.name || "");
  if (requestedFamily && candidateFamily && requestedFamily !== candidateFamily) return 0;

  const requestedSizes = materialDimensions(requestedName);
  const candidateSizes = materialDimensions(candidate?.name || "");
  if (requestedSizes.length && candidateSizes.length) {
    const sameSizes = requestedSizes.length === candidateSizes.length &&
      requestedSizes.every((size, index) => size === candidateSizes[index]);
    if (!sameSizes) return 0;
  }

  const candidateSet = new Set(candidateTokens);
  const shared = requestedTokens.filter(token => candidateSet.has(token));
  let score = (shared.length / Math.max(requestedTokens.length, candidateTokens.length)) * 70;

  if (requestedFamily && requestedFamily === candidateFamily) score += 20;
  if (requestedSizes.length && candidateSizes.length) score += 10;
  if (candidate?.url) score += 4;
  if (savedMaterialPrice(candidate) > 0) score += 4;
  if (String(candidate?.last_status || "").toLowerCase().includes("live")) score += 2;

  return Math.min(100, Math.round(score));
}

function findBestSavedMaterialMatch(name) {
  const candidates = [
    ...(Array.isArray(SAVED_MATERIAL_DB) ? SAVED_MATERIAL_DB : []),
    ...(Array.isArray(MATERIAL_LIBRARY) ? MATERIAL_LIBRARY : [])
  ];

  const seen = new Set();
  let best = null;

  for (const candidate of candidates) {
    const key = `${candidate?.name || ""}|${candidate?.supplier || ""}|${candidate?.url || ""}`;
    if (!candidate?.name || seen.has(key)) continue;
    seen.add(key);

    const score = scoreSavedMaterialMatch(name, candidate);
    if (!best || score > best.score) best = {candidate, score};
  }

  return best && best.score >= 72 ? best : null;
}

function enrichMaterialFromSavedDatabase(material) {
  if (!material || !material.name) return material;
  const currentPrice = Number(material.manual_price || material.price || 0);
  const currentUrl = String(material.url || "").trim();

  // Preserve an already confirmed live product.
  if (currentUrl && currentPrice > 0) return material;

  const match = findBestSavedMaterialMatch(material.name);
  if (!match) {
    material.database_match_status = "not_found";
    material.database_match_score = 0;
    return material;
  }

  const saved = match.candidate;
  const savedPrice = savedMaterialPrice(saved);

  material.original_requested_name = material.original_requested_name || material.name;
  material.name = saved.name || material.name;
  material.supplier = saved.supplier || material.supplier || "City Plumbing";
  material.url = saved.url || material.url || "";
  material.manual_price = savedPrice || currentPrice || 0;
  material.price = savedPrice || Number(material.price || 0);
  material.data_source = saved.url ? "saved_database_match" : (material.data_source || "saved_database_match");
  material.source = material.data_source;
  material.database_match_status = "matched";
  material.database_match_score = match.score;
  material.material_confidence = Math.max(Number(material.material_confidence || 0), match.score);
  material.price_status = saved.last_status || material.price_status || (savedPrice ? "cached" : "unpriced");
  material.saved_material_id = saved.id || material.saved_material_id || null;

  return material;
}

function enrichDraftMaterialsFromSavedDatabase(draft) {
  if (!draft || !Array.isArray(draft.materials)) return draft;
  draft.materials = draft.materials.map(item => enrichMaterialFromSavedDatabase(item));
  return draft;
}

function materialAliasInfo(name) {
  const cleaned = cleanMaterialNameForMatching(name);
  for (const rule of MATERIAL_ALIAS_RULES) {
    if ((rule.keywords || []).some(k => cleaned.includes(k))) {
      return { canonical: rule.canonical, category: rule.category || "other", matched: true };
    }
  }
  return { canonical: cleaned || (name || "").trim().toLowerCase(), category: "other", matched: false };
}

function canonicalMaterialName(name) {
  return materialAliasInfo(name).canonical;
}


let SAVED_QUOTES = [];
let SAVED_INVOICES = [];
let SAVED_CUSTOMERS = [];
let SAVED_LEADS = [];
let SAVED_MATERIAL_DB = [];
let CURRENT_QUOTE_ID = null;
let QUOTE_CREATE_IN_PROGRESS = false;
let CURRENT_LEAD_ID = null;
let CURRENT_QUOTE_DATA = null;
let CURRENT_INVOICE_ID = null;
let CURRENT_EDITING_INVOICE_ID = null;

function showNotice(message, type = "success") {
  const box = document.getElementById("appNotice");
  if (!box) return;
  box.className = "notice " + (type === "error" ? "error" : "success");
  box.innerText = message || "";
  box.style.display = message ? "block" : "none";
  if (message) {
    window.clearTimeout(showNotice._timer);
    showNotice._timer = window.setTimeout(() => {
      box.style.display = "none";
      box.innerText = "";
    }, 2600);
  }
}

function clearNotice() {
  const box = document.getElementById("appNotice");
  if (!box) return;
  box.style.display = "none";
  box.innerText = "";
}

function pounds(value) {
  return String.fromCharCode(163) + Number(value || 0).toFixed(2);
}

function escapeHtml(text) {
  return (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function showNotice(message) {
  const box = document.getElementById("notice");
  if (!box) return;
  box.innerText = message;
  box.style.display = "block";
  if (typeof updateQuantityLearningNotes === 'function') if (typeof updateQuantityLearningNotes === 'function') updateQuantityLearningNotes();
  setTimeout(() => { box.style.display = "none"; }, 4000);
}

function showTab(id) {
  document.querySelectorAll(".tab-panel").forEach(x => x.classList.remove("active"));
  const panel = document.getElementById(id);
  if (panel) panel.classList.add("active");

  if (id === "dashboardTab") loadDashboard();
  if (id === "quotesTab") loadHistory();
  if (id === "invoicesTab") loadInvoices();
  if (id === "customersTab") loadCustomers();
  if (id === "leadsTab") loadLeads();
  if (id === "pipelineTab") loadPipeline();
  if (id === "diaryTab") loadDiary();
  if (id === "safetyTab") loadSafety();
  if (id === "materialsDbTab") loadMaterialDb();
  if (id === "intelligenceTab") loadIntelligence();
  if (id === "quotesTab") renderMasterMaterialSuggestions();
}

function toggleBathroomFields() {
  const quoteType = document.getElementById("quote_type").value;
  const bathroomFields = document.getElementById("bathroomFields");
  if (quoteType === "bathroom") bathroomFields.classList.remove("hidden");
  else bathroomFields.classList.add("hidden");
}

function renderTemplates() {
  const box = document.getElementById("templateButtons");
  box.innerHTML = JOB_TEMPLATES.map((t, i) => `
    <button type="button" class="btn-template" onclick="applyTemplate(${i})">${escapeHtml(t.name)}</button>
  `).join("");
}

function renderFavourites() {
  const box = document.getElementById("favouriteButtons");
  box.innerHTML = FAVOURITE_MATERIALS.map((t, i) => `
    <button type="button" class="btn-template" onclick="addFavouriteMaterial(${i})">${escapeHtml(t.name)}</button>
  `).join("");
}

function resolveTemplateMaterial(templateItem) {
  const wanted = (templateItem.name || "").toLowerCase();
  let item = MATERIAL_LIBRARY.find(x => (x.name || "").toLowerCase() === wanted)
    || MATERIAL_LIBRARY.find(x => (x.name || "").toLowerCase().includes(wanted));

  if (!item) {
    item = { name: templateItem.name || "Material", supplier: "", default_price: 0, url: "" };
  }

  return {
    name: item.name || templateItem.name || "Material",
    supplier: item.supplier || templateItem.supplier || "",
    url: item.url || templateItem.url || "",
    default_price: item.default_price || templateItem.default_price || 0,
    manual_price: item.default_price || templateItem.default_price || 0,
    quantity: templateItem.quantity || 1,
  };
}

function applyTemplate(index) {
  const t = JOB_TEMPLATES[index];
  document.getElementById("quote_type").value = t.quote_type;
  document.getElementById("job").value = t.job;
  document.getElementById("labour").value = t.labour;

  if (Array.isArray(t.materials) && t.materials.length) {
    if (confirm("Load the usual material kit for " + t.name + "?")) {
      clearMaterials();
      t.materials.forEach(m => addMaterial(resolveTemplateMaterial(m)));
      showNotice("Template material kit loaded.");
    }
  }

  toggleBathroomFields();
  updateLabourSuggestion();
}

function addFavouriteMaterial(index) {
  addMaterial(FAVOURITE_MATERIALS[index]);
}



let LABOUR_INTELLIGENCE_TIMER = null;

function scheduleLabourIntelligence() {
  window.clearTimeout(LABOUR_INTELLIGENCE_TIMER);
  LABOUR_INTELLIGENCE_TIMER = window.setTimeout(loadLabourIntelligence, 500);
}

async function loadLabourIntelligence() {
  const box = document.getElementById("labourIntelligence");
  if (!box) return;

  const job = document.getElementById("job")?.value || "";
  const quoteType = document.getElementById("quote_type")?.value || "";
  const labour = Number(document.getElementById("labour")?.value || 0);

  if (!job.trim() || job.trim().length < 3) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }

  try {
    const res = await fetch(`/api/labour-intelligence?job=${encodeURIComponent(job)}&quote_type=${encodeURIComponent(quoteType)}&labour=${encodeURIComponent(labour)}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderLabourIntelligence(data);
  } catch (e) {
    box.style.display = "none";
    box.innerHTML = "";
  }
}

function renderLabourIntelligence(data) {
  const box = document.getElementById("labourIntelligence");
  if (!box) return;

  if (!data || !Number(data.average_labour || 0)) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }

  const status = data.status || "unknown";
  let border = "#d1d5db";
  let bg = "#f9fafb";
  let title = "Labour intelligence";

  if (status === "too_low") {
    border = "#dc2626";
    bg = "#fef2f2";
    title = "Labour warning";
  } else if (status === "ok") {
    border = "#16a34a";
    bg = "#f0fdf4";
  } else if (status === "high") {
    border = "#f59e0b";
    bg = "#fffbeb";
  }

  const similarHtml = (data.similar_quotes || []).length ? `
    <details style="margin-top:8px;">
      <summary>Similar labour history</summary>
      ${(data.similar_quotes || []).map(q => `
        <div class="history-item" style="padding:8px;margin-top:6px;">
          Quote #${q.id} · Labour ${pounds(q.labour || 0)} · Total ${pounds(q.total_price || 0)}<br>
          <span class="small">${escapeHtml((q.job || "").slice(0, 130))}</span>
        </div>
      `).join("")}
    </details>
  ` : "";

  box.style.display = "block";
  box.style.borderColor = border;
  box.style.background = bg;
  box.innerHTML = `
    <strong>${title}</strong><br>
    Similar jobs found: <strong>${data.similar_count || 0}</strong><br>
    Your average labour: <strong>${pounds(data.average_labour || 0)}</strong><br>
    Usual range: <strong>${pounds(data.low_range || 0)} - ${pounds(data.high_range || 0)}</strong><br>
    Current labour: <strong>${pounds(data.current_labour || 0)}</strong><br>
    ${data.warning ? `<div style="margin-top:6px;"><strong>${escapeHtml(data.warning)}</strong></div>` : ""}
    <div class="history-actions" style="grid-template-columns:1fr;margin-top:8px;">
      <button type="button" class="btn-light" onclick="applyAverageLabour(${Number(data.average_labour || 0)})">Use average labour</button>
    </div>
    ${similarHtml}
  `;
}

function applyAverageLabour(value) {
  if (!value || Number(value) <= 0) return;
  document.getElementById("labour").value = Number(value).toFixed(2);
  scheduleLabourIntelligence();
  showNotice("Average labour applied.");
}


let QUOTE_LEARNING_TIMER = null;
let LAST_LEARNING_DATA = null;

function currentMaterialNames() {
  return [...document.querySelectorAll("#materials .m-name")]
    .map(x => (x.value || "").trim().toLowerCase())
    .filter(Boolean);
}

function scheduleQuoteLearning() {
  window.clearTimeout(QUOTE_LEARNING_TIMER);
  QUOTE_LEARNING_TIMER = window.setTimeout(loadQuoteLearning, 450);
}


function renderMasterMaterialSuggestions() {
  const box = document.getElementById("master-material-library");
  if (!box) return;

  const input = document.getElementById("masterMaterialSearch");
  const q = input ? input.value.trim().toLowerCase() : "";

  const rules = MATERIAL_ALIAS_RULES.filter(rule => {
    if (!q) return true;
    const hay = `${rule.canonical || ""} ${rule.category || ""} ${(rule.keywords || []).join(" ")}`.toLowerCase();
    return hay.includes(q);
  }).slice(0, 24);

  box.innerHTML = rules.length ? rules.map((rule, idx) => `
    <div class="card">
      <strong>${escapeHtml(rule.canonical)}</strong><br>
      <small>${escapeHtml(rule.category || "other")}</small><br>
      <small>Aliases: ${escapeHtml((rule.keywords || []).slice(0, 3).join(", "))}</small>
      <div style="margin-top:8px;">
        <button type="button" class="btn-light" onclick="addMasterMaterialByIndex(${idx})">Add to quote</button>
      </div>
    </div>
  `).join("") : "No master materials found.";

  window.CURRENT_MASTER_MATERIAL_RESULTS = rules;
}

function addMasterMaterialByIndex(index) {
  const list = window.CURRENT_MASTER_MATERIAL_RESULTS || MATERIAL_ALIAS_RULES;
  const item = list[index];
  if (!item) return;
  addMaterial({
    name: item.canonical,
    supplier: "City Plumbing",
    manual_price: 0
  });
  showNotice("Master material added.");
}


function renderQuoteLearning(data) {
  LAST_LEARNING_DATA = data;
  const box = document.getElementById("learningInsights");
  if (!box) return;

  if (!data || !data.query || data.query.trim().length < 3) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }

  const averages = data.averages || {};
  const common = data.common_materials || [];
  const similar = data.similar_quotes || [];
  const currentNames = currentMaterialNames();

  const missing = common.filter(m => {
    const name = (m.name || "").toLowerCase();
    const canonical = canonicalMaterialName(name);
    const already = currentNames.some(n => {
      const existingCanonical = canonicalMaterialName(n);
      return existingCanonical === canonical || n.includes(name) || name.includes(n);
    });
    return !already && Number(m.used_percent || 0) >= 40;
  }).slice(0, 6);

  const materialHtml = common.slice(0, 8).map(m => `
    <div class="history-item" style="padding:8px;margin-top:6px;">
      <strong>${escapeHtml(m.name)}</strong>${m.alias_matched ? ' <span class="badge green">grouped</span>' : ""}<br>
      <span>Used in ${m.used_percent}% of similar quotes · avg qty ${m.average_quantity} · avg unit ${pounds(m.average_unit_price || 0)} · ${escapeHtml(m.category || "other")}</span>
      <div class="history-actions" style="grid-template-columns:1fr;margin-top:6px;">
        <button type="button" class="btn-light" onclick='addLearningMaterial(${JSON.stringify(m)})'>Add to quote</button>
      </div>
    </div>
  `).join("");

  const missingHtml = missing.length ? `
    <div style="margin-top:10px;padding:10px;border:1px solid #f59e0b;border-radius:12px;background:#fffbeb;">
      <strong>Possible missing materials</strong><br>
      ${missing.map(m => `• ${escapeHtml(m.name)} — used in ${m.used_percent}% of similar quotes`).join("<br>")}
    </div>
  ` : "";

  const bundle = data.suggested_bundle || {};
  const essential = bundle.essential || [];
  const commonBundle = bundle.common || [];
  const optional = bundle.optional || [];
  const bundleItems = [...essential, ...commonBundle];

  const bundleHtml = bundleItems.length ? `
    <div style="margin-top:10px;padding:10px;border:1px solid #16a34a;border-radius:12px;background:#f0fdf4;">
      <strong>Suggested material bundle</strong><br>
      <span class="small">Built from previous similar quotes. Essential = used in 80%+ of similar quotes. Common = used in 40%+.</span>

      <div style="margin-top:8px;">
        ${essential.length ? `<strong>Essential</strong><br>${essential.map(m => `• ${escapeHtml(m.name)} × ${m.average_quantity} (${m.used_percent}%)`).join("<br>")}` : ""}
        ${commonBundle.length ? `<br><strong>Common</strong><br>${commonBundle.map(m => `• ${escapeHtml(m.name)} × ${m.average_quantity} (${m.used_percent}%)`).join("<br>")}` : ""}
      </div>

      <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;">
        <button type="button" class="btn-green" onclick="addLearningBundle('core')">Add Full Bundle</button>
        <button type="button" class="btn-light" onclick="addLearningBundle('essential')">Add Essential Only</button>
      </div>

      ${optional.length ? `
        <details style="margin-top:8px;">
          <summary>Optional extras</summary>
          ${optional.map(m => `
            <div class="history-item" style="padding:8px;margin-top:6px;">
              <strong>${escapeHtml(m.name)}</strong>${m.alias_matched ? ' <span class="badge green">grouped</span>' : ""}<br>
              <span class="small">Used in ${m.used_percent}% · avg qty ${m.average_quantity}</span>
              <div class="history-actions" style="grid-template-columns:1fr;margin-top:6px;">
                <button type="button" class="btn-light" onclick='addLearningMaterial(${JSON.stringify(m)})'>Add optional item</button>
              </div>
            </div>
          `).join("")}
        </details>
      ` : ""}
    </div>
  ` : "";


  const similarHtml = similar.length ? `
    <details style="margin-top:10px;">
      <summary>Similar quotes found (${data.similar_count})</summary>
      ${similar.map(q => `
        <div class="history-item" style="padding:8px;margin-top:6px;">
          <strong>Quote #${q.id}</strong> — ${escapeHtml(q.created_at || "")}<br>
          ${escapeHtml((q.job || "").slice(0, 160))}<br>
          Labour ${pounds(q.labour)} · Materials ${pounds(q.materials)} · Total ${pounds(q.total_price)}
        </div>
      `).join("")}
    </details>
  ` : "";

  box.innerHTML = `
    <strong>Learning from previous quotes</strong><br>
    ${escapeHtml(data.message || "")}<br>
    <div style="margin-top:8px;">
      Avg labour: <strong>${pounds(averages.labour || 0)}</strong> ·
      Avg materials: <strong>${pounds(averages.materials || 0)}</strong> ·
      Avg total: <strong>${pounds(averages.total_price || 0)}</strong>
    </div>
    ${missingHtml}
    ${bundleHtml}
    <details style="margin-top:10px;" ${common.length ? "open" : ""}>
      <summary>Common materials</summary>
      ${materialHtml || "No common materials yet."}
    </details>
    ${similarHtml}
  `;
  box.style.display = "block";
}

async function loadQuoteLearning() {
  const job = document.getElementById("job")?.value || "";
  const quoteType = document.getElementById("quote_type")?.value || "";
  const box = document.getElementById("learningInsights");

  if (!job.trim() || job.trim().length < 3) {
    if (box) {
      box.style.display = "none";
      box.innerHTML = "";
    }
    return;
  }

  try {
    const res = await fetch(`/api/quote-learning?q=${encodeURIComponent(job)}&quote_type=${encodeURIComponent(quoteType)}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderQuoteLearning(data);
    scheduleLabourIntelligence();
  } catch (e) {
    if (box) {
      box.style.display = "block";
      box.innerHTML = "Could not load quote learning.";
    }
  }
}


function materialAlreadyInQuote(materialName) {
  const name = (materialName || "").trim().toLowerCase();
  if (!name) return false;
  const canonical = canonicalMaterialName(name);
  return currentMaterialNames().some(existing => {
    const existingCanonical = canonicalMaterialName(existing);
    return existingCanonical === canonical || existing.includes(name) || name.includes(existing);
  });
}

function addLearningBundle(mode = "core") {
  if (!LAST_LEARNING_DATA || !LAST_LEARNING_DATA.suggested_bundle) {
    alert("No suggested bundle available yet.");
    return;
  }

  const bundle = LAST_LEARNING_DATA.suggested_bundle;
  let items = [];

  if (mode === "essential") {
    items = bundle.essential || [];
  } else {
    items = [...(bundle.essential || []), ...(bundle.common || [])];
  }

  const newItems = items.filter(m => !materialAlreadyInQuote(m.name));

  if (!newItems.length) {
    showNotice("Bundle materials are already in this quote.");
    return;
  }

  newItems.forEach(m => addLearningMaterial(m, false));
  scheduleQuoteLearning();
  showNotice(`${newItems.length} bundle material(s) added.`);
}


function addLearningMaterial(m, refresh = true) {
  addMaterial({
    name: m.name || "",
    quantity: m.average_quantity || 1,
    supplier: m.supplier || "City Plumbing",
    url: m.url || "",
    manual_price: m.average_unit_price || 0,
    default_price: m.average_unit_price || 0,
  });
  if (refresh) scheduleQuoteLearning();
  showNotice("Material added from quote history.");
}

function applyLearningLabour() {
  if (!LAST_LEARNING_DATA || !LAST_LEARNING_DATA.averages) return;
  const labour = Number(LAST_LEARNING_DATA.averages.labour || 0);
  if (labour > 0) {
    document.getElementById("labour").value = labour.toFixed(2);
    showNotice("Average labour applied.");
  }
}


function updateLabourSuggestion() {
  const quoteType = document.getElementById("quote_type").value;
  const text = document.getElementById("job").value.toLowerCase();
  const box = document.getElementById("labourSuggestion");

  let message = "Small jobs: use your judgement and minimum charge where needed.";
  if (quoteType === "bathroom") message = "Typical bathroom labour is often higher. Adjust to suit your job.";
  if (quoteType === "heating") message = "Heating jobs often vary by size and access. Adjust labour as needed.";

  if (quoteType === "small" && text.includes("tap")) message = "Suggested labour: around £120. Typical range: £100 - £140.";
  if (quoteType === "small" && (text.includes("toilet") || text.includes("wc"))) message = "Suggested labour: around £180. Typical range: £160 - £220.";
  if (quoteType === "small" && (text.includes("waste") || text.includes("trap"))) message = "Suggested labour: around £120. Typical range: £90 - £140.";
  if (quoteType === "small" && text.includes("outside tap")) message = "Suggested labour: around £150. Typical range: £140 - £180.";
  if (quoteType === "bathroom" && text.includes("refurb")) message = "Suggested labour: around £2,200. Typical range: £2,000 - £2,800.";
  if (quoteType === "bathroom" && text.includes("install")) message = "Suggested labour: around £1,800. Typical range: £1,600 - £2,200.";
  if (quoteType === "heating" && text.includes("radiator")) message = "Suggested labour: around £180. Typical range: £160 - £220.";
  if (quoteType === "heating" && text.includes("repair")) message = "Suggested labour: around £150. Typical range: £120 - £220.";

  box.innerText = message;
}



function updateMaterialLiveBadge(row) {
  if (!row) return;
  const status = row.querySelector(".material-live-status");
  if (!status) return;
  const url = String(row.querySelector(".m-url")?.value || "").trim();
  const checkedAt = row.dataset.checkedAt || "";
  const sku = row.dataset.sku || "";
  const imageUrl = row.dataset.imageUrl || "";
  if (/^https?:\/\//i.test(url)) {
    status.innerHTML = `
      <span style="display:inline-block;padding:3px 7px;border-radius:999px;background:#dcfce7;color:#166534;font-weight:700;">Live priced</span>
      ${sku ? ` · SKU ${escapeHtml(sku)}` : ""}
      ${checkedAt ? ` · checked ${escapeHtml(new Date(checkedAt).toLocaleString())}` : ""}
      ${imageUrl ? ` · <a href="${escapeHtml(imageUrl)}" target="_blank" rel="noopener">product image</a>` : ""}
    `;
  } else {
    status.innerHTML = `<span style="color:#92400e;">No product URL saved — database and live-product matching did not find a confirmed product.</span>`;
  }
}

async function refreshMaterialRowPrice(button) {
  const row = button.closest(".material-row");
  if (!row) return;
  const url = String(row.querySelector(".m-url")?.value || "").trim();
  const name = String(row.querySelector(".m-name")?.value || "").trim();
  const supplier = String(row.querySelector(".m-supplier")?.value || "").trim();
  if (!/^https?:\/\//i.test(url)) {
    showNotice("Add a confirmed product URL before refreshing the price.");
    return;
  }

  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Checking…";
  try {
    const response = await fetch(
      "/api/live-product-refresh?url=" + encodeURIComponent(url) +
      "&name=" + encodeURIComponent(name) +
      "&supplier=" + encodeURIComponent(supplier)
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Price refresh failed.");
    if (Number(data.live_price || 0) > 0) {
      row.querySelector(".m-manual").value = Number(data.live_price).toFixed(2);
    }
    if (data.name) row.querySelector(".m-name").value = data.name;
    if (data.url) row.querySelector(".m-url").value = data.url;
    if (data.supplier) row.querySelector(".m-supplier").value = data.supplier;
    row.dataset.liveProduct = "1";
    row.dataset.sku = data.sku || row.dataset.sku || "";
    row.dataset.imageUrl = data.image_url || row.dataset.imageUrl || "";
    row.dataset.checkedAt = data.checked_at || new Date().toISOString();
    updateMaterialLiveBadge(row);
    showNotice(Number(data.live_price || 0) > 0 ? "Live price updated." : "Product page confirmed, but no live price was available.");
  } catch (error) {
    showNotice(error.message || "Price refresh failed.");
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function materialQuoteUnitPrice(material) {
  const ruled = applyChargingRuleToMaterial(material || {});
  if (ruled.quote_charge_override !== undefined && ruled.quote_charge_override !== null && Number(ruled.quote_charge_override) >= 0) {
    return Number(ruled.quote_charge_override);
  }
  return Number(ruled.live_price || ruled.manual_price || ruled.default_price || ruled.price || 0);
}

function clearMaterials() {
  const materialsBox = document.getElementById("materials");
  materialsBox.innerHTML = `
    <div id="emptyMaterialsMessage" class="quote-box small" style="background:#f8fafc;">
      No materials added yet. Build the quote with AI or press <strong>+ Add Material</strong>.
    </div>
  `;
  updateForgottenItemWarnings();
}

function changeMaterialQty(button, delta) {
  const row = button.closest(".material-row");
  const input = row?.querySelector(".m-qty");
  if (!input) return;
  const current = Number(input.value || 0);
  const smallStep = current > 0 && current < 1;
  const step = smallStep ? 0.1 : 1;
  input.value = Math.max(0, Math.round((current + delta * step) * 100) / 100);
  input.dispatchEvent(new Event("input", {bubbles:true}));
}

function addMaterial(prefill = null) {
  const emptyMessage = document.getElementById("emptyMaterialsMessage");
  if (emptyMessage) emptyMessage.remove();

  if (prefill) prefill = applySmartQuantityToMaterial(prefill);

  if (prefill) prefill = applyChargingRuleToMaterial(prefill);

  // Consumable/small-part duplicate guard
  if (prefill && prefill.name) {
    const incomingRule = getMaterialChargingRule(prefill.name || "");
    const incomingCanonical = canonicalMaterialName(prefill.name || "");
    if (incomingRule.charge_method === "partial" || incomingRule.charge_method === "small_part") {
      const exists = [...document.querySelectorAll("#materials .m-name")].some(input => canonicalMaterialName(input.value || "") === incomingCanonical);
      if (exists) {
        showNotice(`${incomingCanonical} is already in this quote.`);
        return;
      }
    }
  }
  const div = document.createElement("div");
  div.className = "material-row";
  div.dataset.liveProduct = prefill && prefill.source === "live_merchant_search" ? "1" : "";
  div.dataset.sku = prefill && prefill.sku ? String(prefill.sku) : "";
  div.dataset.imageUrl = prefill && prefill.image_url ? String(prefill.image_url) : "";
  div.dataset.checkedAt = prefill && prefill.checked_at ? String(prefill.checked_at) : "";

  const qty = prefill && prefill.quantity ? prefill.quantity : 1;
  const manualPrice = prefill && prefill.manual_price != null
    ? prefill.manual_price
    : (prefill && prefill.default_price != null ? prefill.default_price : "");

  div.innerHTML = `
    <label>Item name</label>
    <input class="m-name" placeholder="e.g. kitchen tap" value="${prefill ? escapeHtml(prefill.name) : ""}">

    <label>Quantity</label>
    <div style="display:grid;grid-template-columns:52px 1fr 52px;gap:8px;align-items:center;">
      <button type="button" class="btn-light" style="padding:10px 6px;" onclick="changeMaterialQty(this,-1)">−</button>
      <input class="m-qty" type="number" step="0.01" min="0" placeholder="1" value="${qty}" style="text-align:center;margin:0;">
      <button type="button" class="btn-light" style="padding:10px 6px;" onclick="changeMaterialQty(this,1)">+</button>
    </div>

    <label>Supplier</label>
    <select class="m-supplier">
      <option value="City Plumbing">City Plumbing</option>
      <option value="Screwfix">Screwfix</option>
      <option value="Toolstation">Toolstation</option>
      <option value="Topps Tiles">Topps Tiles</option>
      <option value="Selco">Selco</option>
    </select>

    <label>Product URL</label>
    <input class="m-url" placeholder="https://..." value="${prefill && prefill.url ? escapeHtml(prefill.url) : ""}">

    <label>Manual price (£)</label>
      <div class="small charging-note"></div>
      <div class="small quantity-learning-note"></div>
    <input class="m-manual" type="number" step="0.01" placeholder="0" value="${manualPrice}">

    <div class="material-live-status small" style="margin-top:8px;"></div>
    <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
      <button type="button" class="btn-light refresh-material-price" onclick="refreshMaterialRowPrice(this)">Update price</button>
      <button type="button" class="btn-red" onclick="this.closest('.material-row').remove(); refreshAfterBundleChange()">Remove</button>
    </div>
  `;
  document.getElementById("materials").appendChild(div);

  if (prefill) {
    div.querySelector(".m-supplier").value = prefill.supplier || "City Plumbing";
  }
  updateMaterialLiveBadge(div);
  updateForgottenItemWarnings();
  updateSupplierPreferenceNotes();
}



let MATERIAL_SEARCH_TIMER = null;

function renderMaterialSearchResults(results) {
  const resultsBox = document.getElementById("searchResults");

  if (!results.length) {
    resultsBox.innerHTML = `<div class="search-item">No matches found</div>`;
    resultsBox.classList.remove("hidden");
    return;
  }

  resultsBox.innerHTML = results.map((item) => {
    const source = item.source === "saved" ? "saved database" : "built-in";
    const status = item.last_status ? " · " + escapeHtml(item.last_status) : "";
    const used = item.times_used ? " · used " + item.times_used + "x" : "";
    return `
      <div class="search-item" style="touch-action:manipulation;cursor:pointer;" onpointerdown='event.preventDefault(); addMaterialFromLibrary(${JSON.stringify(item)})'>
        <strong>${escapeHtml(item.name)}</strong><br>
        <span class="small">${escapeHtml(item.supplier || "")} · ${pounds(item.default_price || 0)} · ${source}${status}${used}</span>
      </div>
    `;
  }).join("");

  resultsBox.classList.remove("hidden");
}

function localMaterialSearch(query) {
  const terms = query.split(" ").filter(Boolean);
  return MATERIAL_LIBRARY.filter(item => {
    const hay = ((item.name || "") + " " + (item.supplier || "") + " " + (item.url || "")).toLowerCase();
    return terms.every(term => hay.includes(term));
  }).slice(0, 15);
}


function toggleManualMaterialSearch() {
  const panel = document.getElementById("manualMaterialSearchPanel");
  if (!panel) return;

  const isClosed = panel.style.display === "none" || !panel.style.display;
  panel.style.display = isClosed ? "block" : "none";

  if (isClosed) {
    const input = document.getElementById("materialSearch");
    if (input) {
      setTimeout(() => input.focus(), 50);
    }
  }
}

function searchMaterials() {
  const query = document.getElementById("materialSearch").value.trim().toLowerCase();
  const resultsBox = document.getElementById("searchResults");

  if (!query) {
    resultsBox.classList.add("hidden");
    resultsBox.innerHTML = "";
    return;
  }

  renderMaterialSearchResults(localMaterialSearch(query));

  window.clearTimeout(MATERIAL_SEARCH_TIMER);
  MATERIAL_SEARCH_TIMER = window.setTimeout(async () => {
    try {
      const res = await fetch("/api/material-search?q=" + encodeURIComponent(query));
      if (!res.ok) return;
      const results = await res.json();

      // Keep new saved DB items in the browser list too, so future typing feels instant.
      const seen = new Set(MATERIAL_LIBRARY.map(x => `${(x.name||"").toLowerCase()}|${(x.supplier||"").toLowerCase()}|${x.url||""}`));
      results.forEach(item => {
        const key = `${(item.name||"").toLowerCase()}|${(item.supplier||"").toLowerCase()}|${item.url||""}`;
        if (!seen.has(key)) {
          MATERIAL_LIBRARY.push(item);
          seen.add(key);
        }
      });

      renderMaterialSearchResults(results);
    } catch (e) {
      // Keep local results if backend search fails.
    }
  }, 250);
}

function addMaterialFromLibrary(item) {
  addMaterial(item);
  document.getElementById("materialSearch").value = "";
  document.getElementById("searchResults").classList.add("hidden");
  document.getElementById("searchResults").innerHTML = "";
}



function normaliseTemplateNameForDedup(name) {
  return (name || "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\breplace\b/g, "")
    .replace(/\breplacement\b/g, "")
    .replace(/\binstall\b/g, "")
    .replace(/\bfit\b/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function templatePriority(t) {
  let score = 0;
  if (t.source === "trade_knowledge") score += 100;
  if (t.risk_notes && t.risk_notes.length) score += 20;
  if (t.materials && t.materials.length) score += t.materials.length;
  if (t.essential && t.essential.length) score += t.essential.length;
  if ((t.name || "").toLowerCase().includes("toilet replacement")) score += 10;
  return score;
}

function getCleanJobTemplates() {
  const map = new Map();

  JOB_TEMPLATES.forEach(t => {
    let key = normaliseTemplateNameForDedup(t.name);

    // Merge obvious naming variants.
    if (key === "toilet" || key === "toilet ") key = "toilet";
    if ((t.name || "").toLowerCase() === "replace toilet") key = "toilet";
    if ((t.name || "").toLowerCase() === "toilet replacement") key = "toilet";

    const existing = map.get(key);
    if (!existing || templatePriority(t) > templatePriority(existing)) {
      map.set(key, t);
    }
  });

  return Array.from(map.values());
}


function findBestMaterialForTemplate(name) {
  const target = (name || "").toLowerCase().trim();
  if (!target) return null;

  const targetCanonical = canonicalMaterialName(target);
  const saved = MATERIAL_LIBRARY.filter(x => x.source === "saved");

  let found = saved.find(x => canonicalMaterialName(x.name || "") === targetCanonical);
  if (found) return found;

  found = saved.find(x => (x.name || "").toLowerCase() === target);
  if (found) return found;

  found = saved.find(x => (x.name || "").toLowerCase().includes(target) || target.includes((x.name || "").toLowerCase()));
  if (found) return found;

  found = MATERIAL_LIBRARY.find(x => canonicalMaterialName(x.name || "") === targetCanonical);
  if (found) return found;

  found = MATERIAL_LIBRARY.find(x => (x.name || "").toLowerCase() === target);
  if (found) return found;

  found = MATERIAL_LIBRARY.find(x => (x.name || "").toLowerCase().includes(target) || target.includes((x.name || "").toLowerCase()));
  return found || { name: name, quantity: 1, supplier: "City Plumbing", default_price: 0 };
}

function applyJobTemplate(templateName) {
  const template = getCleanJobTemplates().find(t => t.name === templateName);
  if (!template) return;

  document.getElementById("quote_type").value = template.quote_type || "small";
  let jobText = template.job || "";
  if (template.risk_notes && template.risk_notes.length) {
    jobText += "\n\nNotes to check:\n" + template.risk_notes.map(n => "- " + n).join("\n");
  }
  document.getElementById("job").value = jobText;
  document.getElementById("labour").value = template.labour || "";
  toggleBathroomFields();
  updateLabourSuggestion();
  scheduleQuoteLearning();

  const materialsBox = document.getElementById("materials");
  materialsBox.innerHTML = "";

  (template.materials || []).forEach(templateMaterial => {
    const material = findBestMaterialForTemplate(templateMaterial.name);
    addMaterial({
      ...material,
      quantity: templateMaterial.quantity || 1,
      manual_price: material.default_price || material.last_price || material.last_live_price || material.last_manual_price || 0
    });
  });

  const search = document.getElementById("templateSearch");
  const results = document.getElementById("templateSearchResults");
  if (search) search.value = "";
  if (results) {
    results.classList.add("hidden");
    results.innerHTML = "";
  }

  showNotice("Template loaded: " + template.name);
}


function getMaterialAliasKeywordsForTemplate(t) {
  const materialNames = [];
  (t.materials || []).forEach(m => materialNames.push(m.name || ""));
  (t.essential || []).forEach(m => materialNames.push(m.name || ""));
  (t.common || []).forEach(m => materialNames.push(m.name || ""));
  (t.optional || []).forEach(m => materialNames.push(m.name || ""));

  const keywords = [];
  materialNames.forEach(name => {
    const alias = materialAliasInfo(name);
    keywords.push(name);
    keywords.push(alias.canonical || "");
    keywords.push(alias.category || "");

    MATERIAL_ALIAS_RULES.forEach(rule => {
      if ((rule.canonical || "").toLowerCase() === (alias.canonical || "").toLowerCase()) {
        keywords.push(rule.canonical || "");
        (rule.keywords || []).forEach(k => keywords.push(k));
      }
    });
  });

  return keywords.join(" ");
}

function getTemplateSearchHaystack(t) {
  return [
    t.name || "",
    t.category || "",
    t.quote_type || "",
    t.job || "",
    (t.search_terms || []).join(" "),
    (t.risk_notes || []).join(" "),
    getMaterialAliasKeywordsForTemplate(t)
  ].join(" ").toLowerCase();
}

function expandTradeSearchTerms(q) {
  const raw = (q || "").toLowerCase().trim();
  const expansions = [raw];

  const rules = [
    [["aav", "auto air vent", "automatic air vent", "air vent"], "automatic air vent aav heating leak pressure loss air vent replacement"],
    [["filling loop", "fill loop", "boiler filling loop"], "system repressurisation boiler pressure low pressure top up pressure braided filling loop"],
    [["pressure dropping", "low pressure", "boiler pressure", "pressure loss", "keeps losing pressure"], "system repressurisation filling loop heating leak prv expansion vessel"],
    [["prv", "pressure relief", "overflow pipe dripping", "discharge pipe"], "pressure relief valve prv discharge expansion vessel pressure loss"],
    [["expansion vessel", "vessel", "ev"], "expansion vessel pressure dropping low pressure prv"],
    [["trv", "thermostatic radiator valve"], "thermostatic radiator valve angled trv radiator valve replace trv"],
    [["lockshield"], "lockshield valve radiator valve balancing"],
    [["rad"], "radiator"],
    [["leaking radiator", "radiator leak", "leaking rad"], "heating leak repair trv lockshield valve radiator valve"],
    [["not heating", "cold radiator", "cold rad", "air lock"], "cold radiator diagnosis radiator not heating bleed valve stuck trv balancing"],
    [["bleed", "bleeding radiator"], "radiator bleed valve air in radiator cold radiator"],
  ];

  rules.forEach(([triggers, extra]) => {
    if (triggers.some(trigger => raw.includes(trigger))) expansions.push(extra);
  });

  return expansions.join(" ");
}


function renderTemplateSearch() {
  const input = document.getElementById("templateSearch");
  const box = document.getElementById("templateSearchResults");
  if (!input || !box) return;

  const q = input.value.trim().toLowerCase();
  if (!q) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }

  const expandedQuery = expandTradeSearchTerms(q);
  const rawTerms = q.toLowerCase().split(/\s+/).filter(Boolean);
  const expandedTerms = expandedQuery.split(/\s+/).filter(Boolean);

  function templateScore(t) {
    const hay = getTemplateSearchHaystack(t);
    const name = (t.name || "").toLowerCase();
    const searchTerms = ((t.search_terms || []).join(" ")).toLowerCase();

    let score = 0;

    rawTerms.forEach(term => {
      if (name.includes(term)) score += 30;
      if (searchTerms.includes(term)) score += 25;
      if (hay.includes(term)) score += 8;
    });

    expandedTerms.forEach(term => {
      if (name.includes(term)) score += 8;
      if (searchTerms.includes(term)) score += 6;
      if (hay.includes(term)) score += 2;
    });

    if (hay.includes(q.toLowerCase())) score += 40;
    if (t.category && String(t.category).toLowerCase().includes("heating")) score += 3;
    return score;
  }

  const matches = getCleanJobTemplates()
    .map(t => ({ t, score: templateScore(t) }))
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .map(x => x.t)
    .slice(0, 12);

  if (!matches.length) {
    box.innerHTML = '<div class="search-item">No template found</div>';
    box.classList.remove("hidden");
    return;
  }

  box.innerHTML = matches.map(t => `
    <div class="search-item" onclick='applyJobTemplate(${JSON.stringify(t.name)})'>
      <strong>${escapeHtml(t.name)}</strong><br>
      <span class="small">${t.source === "trade_knowledge" ? "Trade library" : "Saved template"} · Labour: ${pounds(t.labour || 0)} · ${(t.materials || []).length} materials · auto-loads kit</span><br>
      <span class="small">${escapeHtml((t.job || "").slice(0, 120))}</span>
    </div>
  `).join("");
  box.classList.remove("hidden");
}

function clearQuoteMaterials() {
  if (!confirm("Clear all materials from this quote?")) return;
  document.getElementById("materials").innerHTML = "";
  showNotice("Materials cleared.");
}

function duplicateLastMaterial() {
  const rows = [...document.querySelectorAll("#materials .material-row")];
  if (!rows.length) {
    addMaterial();
    return;
  }
  const last = rows[rows.length - 1];
  addMaterial({
    name: last.querySelector(".m-name")?.value || "",
    quantity: last.querySelector(".m-qty")?.value || 1,
    supplier: last.querySelector(".m-supplier")?.value || "City Plumbing",
    url: last.querySelector(".m-url")?.value || "",
    manual_price: last.querySelector(".m-manual")?.value || 0,
  });
  showNotice("Last material duplicated.");
}

function renderTemplateButtons() {
  const box = document.getElementById("templateButtons");
  if (!box) return;
  box.innerHTML = getCleanJobTemplates().slice(0, 16).map(t => `
    <button type="button" class="btn-light" onclick='applyJobTemplate(${JSON.stringify(t.name)})'>${escapeHtml(t.name)}</button>
  `).join("");
}


function normalisePhone(phone) {
  const digits = (phone || "").replace(/\D/g, "");
  if (!digits) return "";
  if (digits.startsWith("44")) return digits;
  if (digits.startsWith("0")) return "44" + digits.slice(1);
  return digits;
}

function setEditingStatus(text = "", show = false) {
  const box = document.getElementById("editingStatus");
  if (show) {
    box.innerText = text;
    box.classList.remove("hidden");
  } else {
    box.innerText = "";
    box.classList.add("hidden");
  }
}

function collectFormPayload() {
  const materials = [];
  document.querySelectorAll(".material-row").forEach(row => {
    const name = row.querySelector(".m-name").value;
    const baseMaterial = {
      name,
      quantity: parseFloat(row.querySelector(".m-qty").value || 1),
      supplier: row.querySelector(".m-supplier").value,
      url: row.querySelector(".m-url").value,
      manual_price: parseFloat(row.querySelector(".m-manual").value || 0)
    };
    const chargedMaterial = applyChargingRuleToMaterial(baseMaterial);
    materials.push(chargedMaterial);
  });

  return {
    quote_type: document.getElementById("quote_type").value,
    lead_id: typeof CURRENT_LEAD_ID === 'undefined' ? null : CURRENT_LEAD_ID,
    source_category: document.getElementById("quote_source")?.value || "",
    work_type: document.getElementById("quote_work_type")?.value || "",
    additional_work_types: typeof b7SelectedAdditional === 'function' ? b7SelectedAdditional('quoteAdditional', document.getElementById('quote_work_type').value) : [],
    customer_name: document.getElementById("customer_name").value,
    customer_email: document.getElementById("customer_email").value,
    customer_address: document.getElementById("customer_address").value,
    customer_phone: document.getElementById("customer_phone").value,
    job_description: document.getElementById("job").value,
    labour_cost: parseFloat(document.getElementById("labour").value || 0),
    include_callout_charge: document.getElementById("include_callout_charge").checked,
    callout_charge: parseFloat(document.getElementById("callout_charge").value || 0),
    include_travel_charge: document.getElementById("include_travel_charge").checked,
    travel_charge: parseFloat(document.getElementById("travel_charge").value || 0),
    include_materials_handling: document.getElementById("include_materials_handling").checked,
    materials_handling_percent: parseFloat(document.getElementById("materials_handling_percent").value || 25),
    materials: materials,
    tiling: document.getElementById("tiling").checked,
    wall_tiling_m2: parseFloat(document.getElementById("wall_tiling_m2").value || 0),
    floor_tiling_m2: parseFloat(document.getElementById("floor_tiling_m2").value || 0),
    wall_height: document.getElementById("wall_height").value,
    customer_supplies_tiles: document.getElementById("customer_supplies_tiles").checked,
    deposit_percent: parseFloat(document.getElementById("deposit_percent").value || 0)
  };
}


function buildQuoteMaterialsWhatsappText(data) {
  const lines = data.material_lines || [];
  if (!lines.length) return "Materials used:\n- No itemised materials listed";

  const rows = lines.map(x => {
    const source = x.price_source || (x.live_price_used ? "live" : "manual");
    const sourceLabel = source === "cached" ? "cached live" : source;
    return `- ${x.name || "Material"}\n  Qty: ${x.quantity || 1} × ${pounds(x.unit_price_used || 0)} each = ${pounds(x.line_total || 0)} (${sourceLabel})`;
  });

  return "Materials used:\n" + rows.join("\n");
}

function buildQuoteWhatsappMessage(data) {
  const quotePdfUrl = CURRENT_QUOTE_ID
    ? `${window.location.origin}/api/quotes/${CURRENT_QUOTE_ID}/pdf`
    : "";

  const pdfLine = quotePdfUrl
    ? `View/download your quote PDF:\n${quotePdfUrl}`
    : "I can send the PDF once the quote is saved.";

  const customerName = data.customer_name ? ` ${data.customer_name}` : "";

  return `Hi${customerName},

Please find your quote below.

Quote total: ${pounds(data.total_price)}

${pdfLine}

If you have any questions, just let me know.

Nigel Harvey Ltd
07595 725547`;
}


function renderQuoteResult(data) {
  CURRENT_QUOTE_DATA = data;
  document.getElementById("invoiceCard").style.display = "none";

  document.getElementById("r_date").innerText = data.created_at || "-";
  document.getElementById("r_type").innerText = data.quote_type || "-";
  document.getElementById("r_customer").innerText = data.customer_name || "-";
  document.getElementById("r_phone").innerText = data.customer_phone || "-";
  document.getElementById("r_address").innerText = data.customer_address || "-";
  document.getElementById("r_job").innerText = data.job || "-";
  document.getElementById("r_labour").innerText = pounds(data.labour);
  const calloutCharge = Number(data.callout_charge || 0);
  document.getElementById("r_callout").innerText = pounds(calloutCharge);
  document.getElementById("r_callout_row").style.display = calloutCharge > 0 ? "flex" : "none";
  const travelCharge = Number(data.travel_charge || 0);
  document.getElementById("r_travel").innerText = pounds(travelCharge);
  document.getElementById("r_travel_row").style.display = travelCharge > 0 ? "flex" : "none";
  document.getElementById("r_materials").innerText = pounds(data.materials);

  const materialsBase = data.materials_base != null ? Number(data.materials_base) : Number(data.materials || 0);
  const procurementAmount = Number(data.materials_procurement_amount || 0);
  const procurementPercent = Number(data.materials_procurement_percent || 0);
  document.getElementById("r_materials_base").innerText = pounds(materialsBase);
  document.getElementById("r_procurement_amount").innerText = pounds(procurementAmount);
  document.getElementById("r_procurement_percent").innerText = procurementPercent > 0 ? "(" + procurementPercent.toFixed(0) + "%)" : "";
  document.getElementById("r_procurement_row").style.display = procurementAmount > 0 ? "flex" : "none";

  document.getElementById("r_deposit").innerText = data.deposit_amount ? pounds(data.deposit_amount) + " (" + Number(data.deposit_percent).toFixed(0) + "%)" : String.fromCharCode(163) + "0.00";
  document.getElementById("r_total").innerText = pounds(data.total_price);

  const lines = data.material_lines || [];
  document.getElementById("r_material_lines").innerHTML = lines.length
    ? lines.map(x => {
        const source = x.price_source || (x.live_price_used ? "live" : "manual");
        const badge = source === "live"
          ? '<span class="badge green">live</span>'
          : (source === "cached" ? '<span class="badge green">cached live</span>' : '<span class="badge">manual</span>');
        return `<div>${escapeHtml(x.name || "")} × ${x.quantity} @ ${pounds(x.unit_price_used || 0)} each — ${pounds(x.line_total)} ${badge}</div>`;
      }).join("")
    : "<div>No materials added.</div>";

  const internalMode = document.getElementById("internal_mode").checked;
  const internalBox = document.getElementById("internalBox");
  if (internalMode) {
    internalBox.classList.remove("hidden");
    document.getElementById("r_internal_raw").innerText = pounds(data.internal_raw_materials);
    document.getElementById("r_internal_job_multiplier").innerText = data.internal_job_multiplier + "x";
    document.getElementById("r_internal_after_job").innerText = pounds(data.internal_after_job_markup);
    document.getElementById("r_internal_handling_percent").innerText = data.internal_handling_percent + "%";
    document.getElementById("r_internal_after_handling").innerText = pounds(data.internal_after_handling);
    document.getElementById("r_internal_hidden_uplift").innerText = pounds(data.internal_hidden_uplift);
    document.getElementById("r_internal_profit").innerText = pounds(data.gross_profit);
    document.getElementById("r_internal_margin").innerText = Number(data.margin_percent || 0).toFixed(1) + "%";
  } else {
    internalBox.classList.add("hidden");
  }

  const message = buildQuoteWhatsappMessage(data);

  const cleanPhone = normalisePhone(data.customer_phone || "");
  document.getElementById("whatsappBtn").href = cleanPhone
    ? "https://wa.me/" + cleanPhone + "?text=" + encodeURIComponent(message)
    : "https://wa.me/?text=" + encodeURIComponent(message);

  document.getElementById("resultCard").style.display = "block";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderStatusBadge(status) {
  const s = (status || "").toLowerCase();
  if (s === "paid") return '<span class="badge green">Paid</span>';
  if (s === "part paid") return '<span class="badge orange">Part Paid</span>';
  return '<span class="badge red">Unpaid</span>';
}


function renderInvoicePhotoGallery(photos) {
  const box = document.getElementById("invoicePhotoGallery");
  if (!box) return;
  const items = photos || [];
  if (!items.length) {
    box.innerHTML = `<div class="small">No job photos attached yet.</div>`;
    return;
  }
  box.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;">
      ${items.map(photo => `
        <div style="border:1px solid #d1d5db;border-radius:10px;background:white;padding:8px;">
          <img src="${escapeHtml(photo.url || "")}" alt="" loading="lazy"
            style="width:100%;height:130px;object-fit:cover;border-radius:7px;background:#f3f4f6;">
          <strong style="display:block;margin-top:7px;">${escapeHtml(photo.category_label || "Job photo")}</strong>
          <span class="small">${escapeHtml(photo.caption || "")}</span>
          <button type="button" class="btn-red" style="margin-top:8px;width:100%;"
            onclick="deleteInvoicePhoto(${Number(photo.id || 0)})">Remove</button>
        </div>
      `).join("")}
    </div>`;
}

async function uploadInvoicePhotos() {
  if (!CURRENT_INVOICE_ID) {
    alert("Open or create an invoice first.");
    return;
  }
  const input = document.getElementById("invoicePhotoFiles");
  const files = [...(input?.files || [])];
  if (!files.length) {
    alert("Take or choose at least one photo.");
    return;
  }

  const status = document.getElementById("invoicePhotoUploadStatus");
  const form = new FormData();
  form.append("category", document.getElementById("invoicePhotoCategory")?.value || "after");
  form.append("caption", document.getElementById("invoicePhotoCaption")?.value || "");
  files.forEach(file => form.append("photos", file));

  status.innerHTML = `Preparing and uploading ${files.length} photo${files.length === 1 ? "" : "s"}…`;
  try {
    const response = await fetch(`/api/invoices/${CURRENT_INVOICE_ID}/photos`, {
      method: "POST",
      body: form
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Photo upload failed.");
    if (input) input.value = "";
    const caption = document.getElementById("invoicePhotoCaption");
    if (caption) caption.value = "";
    renderInvoicePhotoGallery(data.photos || []);
    status.innerHTML = `✓ ${Number(data.added || 0)} photo${Number(data.added || 0) === 1 ? "" : "s"} added to the invoice PDF.`;
    showNotice("Job photos added to invoice.");
  } catch (error) {
    status.innerHTML = `<span style="color:#b91c1c;">${escapeHtml(error.message || "Photo upload failed.")}</span>`;
  }
}

async function deleteInvoicePhoto(photoId) {
  if (!CURRENT_INVOICE_ID || !confirm("Remove this photo from the invoice?")) return;
  try {
    const response = await fetch(
      `/api/invoices/${CURRENT_INVOICE_ID}/photos/${photoId}`,
      {method: "DELETE"}
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not remove photo.");
    renderInvoicePhotoGallery(data.photos || []);
    showNotice("Invoice photo removed.");
  } catch (error) {
    alert(error.message || "Could not remove photo.");
  }
}


async function copyInvoiceBankDetails() {
  const details = window.CURRENT_INVOICE_PAYMENT_DETAILS;
  if (!details) return;
  const value = [
    `Bank: ${details.bank}`,
    `Account name: ${details.accountName}`,
    `Sort code: ${details.sortCode}`,
    `Account number: ${details.accountNumber}`,
    `Amount due: ${pounds(details.amount)}`,
    `Reference: ${details.reference}`
  ].join("\n");
  try {
    await navigator.clipboard.writeText(value);
    showNotice("Bank details copied.");
  } catch (error) {
    prompt("Copy these bank details:", value);
  }
}

async function sendCurrentOverdueReminder() {
  if (!CURRENT_INVOICE_ID) return;
  try {
    const response = await fetch(`/api/invoices/${CURRENT_INVOICE_ID}/send-overdue-reminder`, {method:"POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Reminder could not be sent.");
    renderInvoiceCard(data);
    showNotice("Overdue reminder sent.");
  } catch (error) {
    alert(error.message || "Reminder could not be sent.");
  }
}

function renderInvoiceCard(item, scrollToTop = true) {
  CURRENT_INVOICE_ID = item.id;
  document.getElementById("resultCard").style.display = "none";
  document.getElementById("invoiceCard").style.display = "block";
  cancelInvoiceEdit();

  const invoice = item.invoice;
  const quoteResult = item.quote_result;

  document.getElementById("i_number").innerText = item.invoice_number || "-";
  document.getElementById("i_job_reference").innerText = item.job_reference || "-";
  document.getElementById("i_date").innerText = item.created_at || "-";
  document.getElementById("i_due_date").innerText = item.due_date || "-";
  document.getElementById("i_status").innerHTML = renderStatusBadge(item.status);
  document.getElementById("i_customer").innerText = invoice.customer_name || "-";
  document.getElementById("i_phone").innerText = invoice.customer_phone || "-";
  document.getElementById("i_address").innerText = invoice.customer_address || "-";
  document.getElementById("i_job").innerText = invoice.job || "-";
  document.getElementById("i_labour").innerText = pounds(invoice.labour);
  document.getElementById("i_materials").innerText = pounds(invoice.materials);
  document.getElementById("i_total").innerText = pounds(item.total_price);
  document.getElementById("i_paid").innerText = pounds(item.amount_paid);
  document.getElementById("i_balance").innerText = pounds(item.balance_due);
  document.getElementById("i_balance_big").innerText = pounds(item.balance_due);
  renderInvoicePhotoGallery(item.photos || []);

  const paymentBox = document.getElementById("i_payment_link_box");
  const isSmallJob = ((quoteResult.quote_type || "").toLowerCase() === "small");
  const bankDetails = {
    bank: APP_PAYMENT_CONFIG.bank,
    accountName: APP_PAYMENT_CONFIG.accountName,
    sortCode: APP_PAYMENT_CONFIG.sortCode,
    accountNumber: APP_PAYMENT_CONFIG.accountNumber,
    reference: item.invoice_number || "",
    amount: Number(item.balance_due || 0)
  };
  const termsHtml = isSmallJob
    ? `<div class="invoice-note">Please pay by the due date shown above.<br>Late payment fee may be applied after 14 days.<br>Materials remain the property of Nigel Harvey Ltd until paid in full.</div>`
    : `<div class="invoice-note">Please pay by the due date shown above.<br>Late payment fee may be applied after 14 days.<br>Materials remain the property of Nigel Harvey Ltd until paid in full.<br>Deposit required before works begin where applicable.</div>`;

  paymentBox.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr auto;gap:12px;align-items:start;">
      <div>
        <strong>Bank transfer</strong><br>
        Bank: ${escapeHtml(bankDetails.bank)}<br>
        Account name: ${escapeHtml(bankDetails.accountName)}<br>
        Sort code: <strong>${escapeHtml(bankDetails.sortCode)}</strong><br>
        Account number: <strong>${escapeHtml(bankDetails.accountNumber)}</strong><br>
        Reference: <strong>${escapeHtml(bankDetails.reference)}</strong><br>
        Amount due: <strong>${pounds(bankDetails.amount)}</strong>
      </div>
      ${item.qr_available === false ? `
        <div class="small" style="width:112px;padding:10px;border:1px solid #ddd;border-radius:8px;background:#fafafa;">
          QR unavailable<br>Install qrcode[pil]
        </div>
      ` : `
        <img src="/api/invoices/${item.id}/payment-qr" alt="Payment details QR"
          onerror="this.style.display='none'"
          style="width:112px;height:112px;border:1px solid #ddd;border-radius:8px;background:white;">
      `}
    </div>
    <div class="history-actions" style="grid-template-columns:1fr;margin-top:8px;">
      <button type="button" class="btn-light" onclick="copyInvoiceBankDetails()">Copy bank details</button>
    </div>
    <div class="small" style="margin-top:6px;">The QR contains the bank details, outstanding amount and invoice reference. Bank-app support for automatic prefilling varies.</div>
    ${item.payment_link ? `<div style="margin-top:8px;"><strong>Payment link:</strong> <a href="${escapeHtml(item.payment_link)}" target="_blank">${escapeHtml(item.payment_link)}</a></div>` : ""}
    ${termsHtml}
  `;
  const watermark = document.getElementById("invoicePaidWatermark");
  if (watermark) watermark.classList.toggle("hidden", String(item.status || "").toLowerCase() !== "paid");
  window.CURRENT_INVOICE_PAYMENT_DETAILS = bankDetails;

  const invoiceUrl = window.location.origin + "/invoice/" + item.id;

  const msg =
`Nigel Harvey Ltd Invoice

Invoice: ${item.invoice_number}
Customer: ${invoice.customer_name || "-"}
Balance due: ${pounds(item.balance_due)}

View your invoice:
${invoiceUrl}`;

  const cleanPhone = normalisePhone(invoice.customer_phone || quoteResult.customer_phone || "");
  document.getElementById("invoiceWhatsappBtn").href = cleanPhone
    ? "https://wa.me/" + cleanPhone + "?text=" + encodeURIComponent(msg)
    : "https://wa.me/?text=" + encodeURIComponent(msg);

  document.getElementById("invoiceOpenBtn").href = invoiceUrl;

  if (scrollToTop) window.scrollTo({ top: 0, behavior: "smooth" });
}

function downloadCurrentQuotePdf() {
  if (!CURRENT_QUOTE_ID) { window.print(); return; }
  window.open(`/api/quotes/${CURRENT_QUOTE_ID}/pdf`, "_blank");
}

function downloadCurrentInvoicePdf() {
  if (!CURRENT_INVOICE_ID) { window.print(); return; }
  window.open(`/api/invoices/${CURRENT_INVOICE_ID}/pdf`, "_blank");
}

async function sendInvoiceEmail() {
  if (!CURRENT_INVOICE_ID) return;
  const toEmail = prompt("Send invoice PDF to which email address?");
  if (!toEmail) return;
  const customMessage = prompt("Optional message to include in the email:", "Please find your invoice attached as a PDF.") || "";
  try {
    const r = await fetch(`/api/invoices/${CURRENT_INVOICE_ID}/send-email`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ to_email: toEmail, message: customMessage })
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Failed to send email");
    showNotice("Invoice email sent successfully.");
  } catch (e) {
    alert(e.message || "Failed to send email");
  }
}

function setQuoteButtonMode(isEditing = false) {
  const btn = document.querySelector('#quotesTab button[onclick="generateQuote()"]');
  if (btn) btn.innerText = isEditing ? "Update Quote" : "Generate Quote";
}

function resetQuoteFormState() {
  CURRENT_QUOTE_ID = null;
  CURRENT_LEAD_ID = null;
  clearAIQuoteDraftState();
  setEditingStatus("", false);
  setQuoteButtonMode(false);
  document.getElementById('quoteWorkflow').innerText = 'New quotes start Pending. Save a quote to track follow-up and outcome.';
}

function fillFormFromRequest(requestData, quoteId = null) {
  clearAIQuoteDraftState();
  CURRENT_LEAD_ID = requestData.lead_id || null;
  document.getElementById("quote_source").value = requestData.source_category || "";
  document.getElementById("quote_work_type").value = requestData.work_type || "";
  b7SetAdditional('quoteAdditional', requestData.additional_work_types || [], requestData.work_type || '');
  document.getElementById("quote_type").value = requestData.quote_type || "small";
  document.getElementById("customer_name").value = requestData.customer_name || "";
  document.getElementById("customer_address").value = requestData.customer_address || "";
  document.getElementById("customer_phone").value = requestData.customer_phone || "";
  document.getElementById("customer_email").value = requestData.customer_email || "";
  document.getElementById("job").value = requestData.job_description || "";
  document.getElementById("labour").value = requestData.labour_cost || "";
  document.getElementById("include_callout_charge").checked = !!requestData.include_callout_charge;
  document.getElementById("callout_charge").value = requestData.callout_charge != null ? requestData.callout_charge : 200;
  document.getElementById("include_travel_charge").checked = !!requestData.include_travel_charge;
  document.getElementById("travel_charge").value = requestData.travel_charge != null ? requestData.travel_charge : 0;
  document.getElementById("include_materials_handling").checked = !!requestData.include_materials_handling;
  document.getElementById("materials_handling_percent").value = String(requestData.materials_handling_percent || 25);
  document.getElementById("tiling").checked = !!requestData.tiling;
  document.getElementById("wall_tiling_m2").value = requestData.wall_tiling_m2 || "";
  document.getElementById("floor_tiling_m2").value = requestData.floor_tiling_m2 || "";
  document.getElementById("wall_height").value = requestData.wall_height || "half";
  document.getElementById("customer_supplies_tiles").checked = !!requestData.customer_supplies_tiles;
  document.getElementById("deposit_percent").value = String(requestData.deposit_percent || 0);

  clearMaterials();
  const materials = requestData.materials || [];
  if (materials.length) materials.forEach(item => addMaterial(item));

  CURRENT_QUOTE_ID = quoteId;
  if (quoteId) {
    setEditingStatus("Editing saved quote #" + quoteId, true);
    setQuoteButtonMode(true);
  } else {
    setEditingStatus("", false);
    setQuoteButtonMode(false);
  }

  toggleBathroomFields();
  updateLabourSuggestion();
  showTab("quotesTab");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderProfitChart(data) {
  const box = document.getElementById("profitChart");
  if (!data || !data.length) {
    box.innerHTML = "No monthly data yet.";
    return;
  }

  const maxValue = Math.max(...data.map(x => x.profit), 1);
  box.innerHTML = data.map(x => {
    const width = Math.max(4, Math.round((x.profit / maxValue) * 100));
    return `
      <div style="margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;gap:10px;">
          <span>${escapeHtml(x.label)}</span>
          <strong>${pounds(x.profit)}</strong>
        </div>
        <div style="background:#e9e9e9;border-radius:999px;height:10px;margin-top:6px;overflow:hidden;">
          <div style="background:#1f7a1f;height:10px;width:${width}%;"></div>
        </div>
      </div>
    `;
  }).join("");
}

function renderDashboardSummary(data) {
  const box = document.getElementById("dashboardSummary");
  if (!box) return;
  if (!data || !data.length) {
    box.innerHTML = "";
    return;
  }

  const sorted = [...data].sort((a, b) => Number(b.profit || 0) - Number(a.profit || 0));
  const best = sorted[0];
  const worst = sorted[sorted.length - 1];

  box.innerHTML = `
    <div class="dashboard-item">
      <div class="small">Best profit month</div>
      <div><strong>${escapeHtml(best.label || "-")}</strong></div>
      <div class="num">${pounds(best.profit || 0)}</div>
    </div>
    <div class="dashboard-item">
      <div class="small">Lowest profit month</div>
      <div><strong>${escapeHtml(worst.label || "-")}</strong></div>
      <div class="num">${pounds(worst.profit || 0)}</div>
    </div>
  `;
}

async function loadDashboard() {
  try {
    const [res, chartRes] = await Promise.all([
      fetch("/api/dashboard"),
      fetch("/api/dashboard/monthly-profit")
    ]);
    const data = await res.json();
    const chartData = await chartRes.json();
    document.getElementById("dashboardMonth").innerText = data.month_label || "";
    document.getElementById("dashboardGrid").innerHTML = `
      <div class="dashboard-item"><div class="small">Quotes this month</div><div class="num">${data.quote_count}</div></div>
      <div class="dashboard-item"><div class="small">Quoted total</div><div class="num">${pounds(data.quoted_total)}</div></div>
      <div class="dashboard-item"><div class="small">Gross profit</div><div class="num">${pounds(data.gross_profit_total)}</div></div>
      <div class="dashboard-item"><div class="small">Average quote</div><div class="num">${pounds(data.avg_quote)}</div></div>
      <div class="dashboard-item"><div class="small">Invoices this month</div><div class="num">${data.invoice_count}</div></div>
      <div class="dashboard-item"><div class="small">Invoiced total</div><div class="num">${pounds(data.invoiced_total)}</div></div>
      <div class="dashboard-item"><div class="small">Paid this month</div><div class="num">${pounds(data.paid_total)}</div></div>
      <div class="dashboard-item"><div class="small">Outstanding</div><div class="num">${pounds(data.balance_total)}</div></div>
      <div class="dashboard-item"><div class="small">Customers</div><div class="num">${data.customer_count}</div></div>
    `;
    renderProfitChart(chartData);
    renderDashboardSummary(chartData);
    const businessResponse = await fetch('/api/business-performance');
    if (businessResponse.ok) renderBusinessReport(await businessResponse.json());
  } catch (e) {
    document.getElementById("profitChart").innerHTML = "Could not load chart.";
    document.getElementById("dashboardSummary").innerHTML = "";
  }
}

function renderRecentQuotes(items) {
  return items.map(x => `<button type="button" class="btn-light" onclick="showTab('quotesTab');loadSavedQuote(${Number(x.id)})">#${Number(x.id)} · ${escapeHtml(x.customer_name || 'Unnamed customer')} · ${pounds(x.total_price)}</button>`).join(' ') || 'None';
}

function renderBusinessReport(data) {
  const counts = data.status_counts;
  const money = data.status_values;
  const follow = data.follow_ups.filter(x => x.due);
  const sourceRows = Object.entries(data.by_source).sort((a,b) => b[1].enquiries - a[1].enquiries);
  document.getElementById('businessReport').innerHTML = `
    <div class="dashboard-grid">
      <div class="dashboard-item">Enquiries <strong>${data.enquiries}</strong></div>
      <div class="dashboard-item">Quotes saved <strong>${data.quotes_saved}</strong></div>
      <div class="dashboard-item">Pending <strong>${counts.pending}</strong> · ${pounds(money.pending)}</div>
      <div class="dashboard-item">Won <strong>${counts.won}</strong> · ${pounds(money.won)}</div>
      <div class="dashboard-item">Lost <strong>${counts.lost}</strong> · ${pounds(money.lost)}</div>
      <div class="dashboard-item">Expired <strong>${counts.expired}</strong></div>
    </div>
    <p>Quoted value ${pounds(data.quoted_value)} · Win rate ${data.win_rate_percent == null ? 'Not enough decided quotes' : data.win_rate_percent + '% (' + data.win_rate_denominator + ' decisions)'}</p>
    <p>Estimated gross profit on won quotes: ${pounds(data.estimated_gross_profit_won)}. This is an estimate, not realised net profit. Historical unclassified quotes: ${counts.unclassified}.</p>
    <h4>Follow up now (${follow.length}; overdue ${follow.filter(x => x.overdue).length})</h4>
    <p>${follow.length ? follow.map(x => `<button type="button" class="btn-light" onclick="showTab('quotesTab');loadSavedQuote(${x.id})">#${x.id} ${escapeHtml(x.date)}${x.overdue ? ' overdue' : ' due'}</button>`).join(' ') : 'No follow-ups due.'}</p>
    <p>Recently won: ${renderRecentQuotes(data.recent_won)}</p>
    <p>Recently lost: ${renderRecentQuotes(data.recent_lost)}</p>
    <h4>Sources</h4><div class="history-list">${sourceRows.map(([source,item]) => `<div class="history-item">${escapeHtml(source)}: ${item.enquiries} enquiries, ${item.quotes} quotes, ${item.wins} wins · won ${pounds(item.won_value)} · invoiced ${pounds(item.invoiced_value)} · paid ${pounds(item.paid_value)}</div>`).join('') || 'No attributable enquiries yet.'}</div>
    <p>Invoice amounts are linked to quotes where possible. Paid amounts are recorded receipts, not net profit; unattributed historical records are excluded from source totals.</p>`;
}

async function deleteCustomer(id) {
  const check = prompt("Type DELETE to confirm");
  if (!check || check.trim().toUpperCase() !== "DELETE") return;

  try {
    const res = await fetch("/api/customers/" + id, {
      method: "DELETE"
    });

    const text = await res.text();
    if (!res.ok) {
      alert("Delete failed: " + text);
      return;
    }

    await loadCustomers();
    await loadHistory();
    await loadInvoices();
    await loadDashboard();

    showNotice("Customer deleted.");
  } catch (e) {
    if (String(e).includes("updateQuantityLearningNotes")) {
      showNotice("Customer deleted.");
      try { await loadCustomers(); } catch (_) {}
    } else {
      alert("Could not delete customer: " + e);
    }
  }
}

async function loadHistory() {
  try {
    const res = await fetch("/api/quotes");
    const data = await res.json();
    SAVED_QUOTES = data;
    const history = document.getElementById("historyList");
    const filter = document.getElementById('quoteStatusFilter')?.value || 'all';
    const dateParts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()).map(p => [p.type,p.value]));
    const today = `${dateParts.year}-${dateParts.month}-${dateParts.day}`;
    const visible = data.filter(q => filter === 'all' || (filter === 'due'
      ? q.status === 'pending' && q.next_follow_up && q.next_follow_up <= today
      : q.status === filter));

    if (!visible.length) {
      history.innerHTML = filter === 'all' ? "No saved quotes yet." : "No quotes match this view.";
      return;
    }

    history.innerHTML = visible.map(q => `
      <div class="history-item">
        <div><strong>#${q.id} ${escapeHtml(q.customer_name || "No customer name")}</strong> · ${renderQuoteStatus(q.status)}</div>
        <div>${escapeHtml(q.job || "")}</div>
        <div class="small">${escapeHtml(q.created_at || "")} · Total ${pounds(q.total_price)} · Profit ${pounds(q.gross_profit)} · Margin ${Number(q.margin_percent || 0).toFixed(1)}%</div>
        <div class="small">${q.lead_id ? 'Lead #' + q.lead_id + ' · ' : ''}${escapeHtml(q.source_category || 'Linked lead source / unknown')} · ${escapeHtml(q.work_type || 'Work type not classified')}${(q.additional_work_types || []).length ? ' + ' + (q.additional_work_types || []).map(escapeHtml).join(', ') : ''}${q.next_follow_up ? ' · Follow up ' + escapeHtml(q.next_follow_up) : ''}${q.loss_reason ? ' · Lost: ' + escapeHtml(q.loss_reason) : ''}</div>
        <div class="row">
          <select id="quote_status_${q.id}" aria-label="Quote status for ${escapeHtml(q.customer_name || 'quote')}">
            ${['pending','won','lost','expired','unclassified'].map(s => `<option value="${s}" ${q.status === s ? 'selected' : ''}>${s[0].toUpperCase() + s.slice(1)}</option>`).join('')}
          </select>
          <input id="quote_follow_${q.id}" type="date" aria-label="Next follow-up date" value="${escapeHtml(q.next_follow_up || '')}">
        </div>
        <div class="row"><select id="quote_loss_${q.id}" aria-label="Reason lost"><option value="">Loss reason (optional)</option>${['Price','Customer chose another contractor','Customer cancelled work','No response','Timing / availability','Job not suitable','Other'].map(s => `<option ${q.loss_reason === s ? 'selected' : ''}>${s}</option>`).join('')}</select><input id="quote_loss_note_${q.id}" maxlength="500" placeholder="Short note (optional)" value="${escapeHtml(q.loss_note || '')}"></div>
        <button type="button" class="btn-blue" onclick="saveQuoteOutcome(${q.id})">Save outcome / follow-up</button>
        <div class="history-actions">
          <button type="button" class="btn-light" onclick="loadSavedQuote(${q.id})">Load</button>
          <button type="button" class="btn-blue" onclick="editSavedQuote(${q.id})">Edit</button>
          <button type="button" class="btn-secondary" onclick="sendSavedQuoteWhatsApp(${q.id})">WhatsApp</button>
          <button type="button" class="btn-blue" onclick="convertQuoteToInvoice(${q.id})">To Invoice</button>
          ${q.status === 'won' ? `<button type="button" class="btn-light" onclick="jobFromQuote(${q.id})">Add to Pipeline</button>` : ''}
          <button type="button" class="btn-light" onclick="printSavedQuote(${q.id})">Print</button>
          <button type="button" class="btn-red" onclick="deleteSavedQuote(${q.id})">Delete</button>
        </div>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("historyList").innerHTML = "Unable to load saved quotes.";
  }
}

async function loadInvoices() {
  try {
    const res = await fetch("/api/invoices");
    const data = await res.json();
    SAVED_INVOICES = data;
    const box = document.getElementById("invoiceList");

    if (!data.length) {
      box.innerHTML = "No invoices yet.";
      return;
    }

    box.innerHTML = data.map(i => `
      <div class="history-item">
        <div><strong>${escapeHtml(i.invoice_number)}</strong> — ${escapeHtml(i.customer_name || "No customer name")}</div>
        <div>${renderStatusBadge(i.status)}</div>
        <div class="small">${escapeHtml(i.created_at || "")} · Total ${pounds(i.total_price)} · Paid ${pounds(i.amount_paid)} · Balance ${pounds(i.balance_due)}</div>
        <div class="small" style="margin-top:4px;"><strong>Job Ref:</strong> ${escapeHtml(i.job_reference || "Not entered")}</div>

        <label style="margin-top:10px;">Update payment</label>
        <div class="row">
          <input id="paid_${i.id}" type="number" step="0.01" placeholder="Amount paid" value="${i.amount_paid || 0}">
          <button type="button" class="btn-blue" style="max-width:180px;" onclick="updateInvoicePaid(${i.id})">Save Amount</button>
        </div>

        <label style="margin-top:10px;">Payment link</label>
        <div class="row">
          <input id="payment_link_${i.id}" type="text" placeholder="https://..." value="${escapeHtml(i.payment_link || "")}">
          <button type="button" class="btn-blue" style="max-width:180px;" onclick="savePaymentLink(${i.id})">Save Link</button>
        </div>

        <div class="history-actions" style="grid-template-columns:repeat(3, 1fr);">
          <button type="button" class="btn-secondary" onclick="markInvoicePaid(${i.id}, ${i.total_price})">Mark Paid</button>
          <button type="button" class="btn-light" onclick="markInvoiceUnpaid(${i.id})">Mark Unpaid</button>
          <button type="button" class="btn-blue" onclick="editInvoice(${i.id})">Edit Invoice / Job Ref</button>
          <button type="button" class="btn-light" onclick="openInvoice(${i.id})">Preview Invoice</button>
          <button type="button" class="btn-secondary" onclick="sendInvoiceWhatsApp(${i.id})">WhatsApp</button>
          <button type="button" class="btn-blue" onclick="emailInvoice(${i.id})">Email</button>
          <button type="button" class="btn-light" onclick="openInvoicePage(${i.id})">Invoice Page</button>
          <button type="button" class="btn-light" onclick="printInvoice(${i.id})">Print</button>
          <button type="button" class="btn-red" onclick="deleteInvoice(${i.id})">Delete</button>
        </div>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("invoiceList").innerHTML = "Unable to load invoices.";
  }
}

function renderQuoteStatus(status) {
  const color = {won:'green',lost:'red',pending:'blue',expired:'orange'}[status] || 'gray';
  return `<span class="badge ${color}">${escapeHtml((status || 'unclassified').toUpperCase())}</span>`;
}

async function saveQuoteOutcome(id) {
  const payload = { status: document.getElementById(`quote_status_${id}`).value,
    next_follow_up: document.getElementById(`quote_follow_${id}`).value,
    loss_reason: document.getElementById(`quote_loss_${id}`).value,
    loss_note: document.getElementById(`quote_loss_note_${id}`).value };
  try {
    const response = await fetch(`/api/quotes/${id}/outcome`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not save outcome');
    await Promise.all([loadHistory(), loadDashboard(), loadLeads()]);
    showNotice('Quote outcome saved.');
  } catch (error) { alert(error.message); }
}

function renderLeadBadge(status) {
  const s = (status || 'new').toLowerCase();
  if (s === 'won') return '<span class="badge green">Won</span>';
  if (s === 'lost') return '<span class="badge red">Lost</span>';
  if (s === 'quoted') return '<span class="badge blue">Quoted</span>';
  if (s === 'contacted') return '<span class="badge orange">Contacted</span>';
  return '<span class="badge gray">New</span>';
}

async function loadLeads() {
  try {
    const res = await fetch('/api/leads');
    const data = await res.json();
    SAVED_LEADS = data;
    const box = document.getElementById('leadList');
    const q = (document.getElementById('leadSearch')?.value || '').trim().toLowerCase();
    const status = (document.getElementById('leadStatusFilter')?.value || 'all').toLowerCase();
    const filtered = data.filter(l => {
      const hay = `${l.id} ${l.name || ''} ${l.phone || ''} ${l.email || ''} ${l.address || ''} ${l.description || ''}`.toLowerCase();
      const statusOk = status === 'all' || (l.status || '').toLowerCase() === status;
      return statusOk && (!q || hay.includes(q));
    });
    if (!filtered.length) {
      box.innerHTML = q || status !== 'all' ? 'No matching leads.' : 'No leads yet.';
      return;
    }
    box.innerHTML = filtered.map(l => `
      <div class="history-item" id="lead_card_${Number(l.id)}">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
          <div><strong>${escapeHtml(l.name || 'Website lead')}</strong></div>
          <div>${renderLeadBadge(l.status)}</div>
        </div>
        <div>${escapeHtml(l.phone || '')}${l.email ? ' · ' + escapeHtml(l.email) : ''}</div>
        <div class="small">${escapeHtml(l.address || '')}</div>
        <div style="margin-top:8px;">${escapeHtml(l.description || '')}</div>
        <div class="small" style="margin-top:8px;">${escapeHtml(l.created_at || '')} · ${escapeHtml((l.job_type || 'small').toUpperCase())} · ${escapeHtml(l.source || 'website')}</div>
        <div class="small">Source: ${escapeHtml(l.source_category || 'Unknown')}${l.work_type ? ' · Primary: ' + escapeHtml(l.work_type) : ''}${(l.additional_work_types || []).length ? ' · Also: ' + l.additional_work_types.map(escapeHtml).join(', ') : ''}</div>
        <div class="row"><select id="lead_source_${l.id}" aria-label="Lead source"><option value="">Automatic source</option>${['Google Business Profile','Google organic search','Website/direct','Referral','Repeat customer','MyBuilder','Locally','Bing','Yell','Checkatrade','TrustATrader','Other'].map(s => `<option ${l.source_category === s ? 'selected' : ''}>${s}</option>`).join('')}</select>
        <select id="lead_work_${l.id}" aria-label="Primary work type" onchange="b7ChangePrimary('lead_additional_${l.id}','lead_work_${l.id}')"><option value="">Primary work type</option>${B7_WORK_TYPES.map(s => `<option ${l.work_type === s ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
        <div id="lead_additional_${l.id}">${b7AdditionalHtml('lead_additional_' + l.id, l.additional_work_types, l.work_type)}</div>
        <button type="button" class="btn-light" onclick="saveLeadClassification(${l.id})">Save source / work type</button>
        ${l.postcode || l.urgency || l.preferred_contact ? `<div class="small">${l.postcode ? 'Postcode: ' + escapeHtml(l.postcode) + ' · ' : ''}${l.urgency ? 'Urgency: ' + escapeHtml(l.urgency) + ' · ' : ''}${l.preferred_contact ? 'Prefers: ' + escapeHtml(l.preferred_contact) : ''}</div>` : ''}
        ${l.landing_page || l.referrer || l.utm_source || l.utm_campaign ? `<div class="small">${l.landing_page ? 'Landing: ' + escapeHtml(l.landing_page) + ' · ' : ''}${l.referrer ? 'Referrer: ' + escapeHtml(l.referrer) + ' · ' : ''}${l.utm_source ? 'Source: ' + escapeHtml(l.utm_source) + ' · ' : ''}${l.utm_campaign ? 'Campaign: ' + escapeHtml(l.utm_campaign) : ''}</div>` : ''}
        <div class="history-actions" style="grid-template-columns:repeat(2,1fr);">
          <button type="button" class="btn-light" onclick="startQuoteFromLead(${l.id})">Start Quote</button>
          <button type="button" class="btn-light" onclick="bookVisitForLead(${l.id})">Book Visit</button>
          <button type="button" class="btn-blue" onclick="updateLeadStatus(${l.id}, 'contacted')">Mark Contacted</button>
        </div>
        <div class="history-actions" style="grid-template-columns:repeat(3,1fr);">
          <button type="button" class="btn-secondary" onclick="updateLeadStatus(${l.id}, 'quoted')">Quoted</button>
          <button type="button" class="btn-secondary" onclick="updateLeadStatus(${l.id}, 'won')">Won</button>
          <button type="button" class="btn-red" onclick="updateLeadStatus(${l.id}, 'lost')">Lost</button>
        </div>
        <div class="history-actions" style="grid-template-columns:1fr 1fr;">
          <a class="btn-link btn-secondary" href="${buildLeadWhatsappHref(l)}" target="_blank">WhatsApp</a>
          <button type="button" class="btn-red" onclick="deleteLead(${l.id})">Delete</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    document.getElementById('leadList').innerHTML = 'Unable to load leads.';
  }
}

function buildLeadWhatsappHref(lead) {
  const cleanPhone = normalisePhone(lead.phone || '');
  const msg = `Hi ${lead.name || ''}, thanks for contacting Nigel Harvey Ltd about: ${lead.description || ''}`.trim();
  return cleanPhone ? `https://wa.me/${cleanPhone}?text=${encodeURIComponent(msg)}` : `https://wa.me/?text=${encodeURIComponent(msg)}`;
}

function startQuoteFromLead(id) {
  const lead = SAVED_LEADS.find(x => x.id === id);
  if (!lead) return;
  startNewQuote();
  CURRENT_LEAD_ID = id;
  document.getElementById('quote_source').value = lead.source_category || '';
  document.getElementById('quote_work_type').value = lead.work_type || '';
  b7SetAdditional('quoteAdditional', lead.additional_work_types || [], lead.work_type || '');
  document.getElementById('customer_name').value = lead.name || '';
  document.getElementById('customer_address').value = lead.address || '';
  document.getElementById('customer_phone').value = lead.phone || '';
  document.getElementById('customer_email').value = lead.email || '';
  document.getElementById('quote_type').value = lead.job_type || 'small';
  document.getElementById('job').value = lead.description || '';
  toggleBathroomFields();
  updateLabourSuggestion();
  scheduleQuoteLearning();
  showTab('quotesTab');
  setEditingStatus('Lead loaded into quote builder. The quote covers the work you enter; scheduling the plumbing job happens after it is won.', true);
}

async function saveLeadClassification(id) {
  const response = await fetch(`/api/leads/${id}/classification`, {method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({source_category:document.getElementById(`lead_source_${id}`).value,
                         work_type:document.getElementById(`lead_work_${id}`).value,
                         additional_work_types:b7SelectedAdditional(`lead_additional_${id}`,
                           document.getElementById(`lead_work_${id}`).value)})});
  if (!response.ok) { const data = await response.json(); alert(data.detail || 'Could not save classification'); return; }
  await Promise.all([loadLeads(), loadDashboard()]);
  showNotice('Lead classification saved.');
}

async function updateLeadStatus(id, status) {
  try {
    const res = await fetch('/api/leads/' + id + '/status', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not update lead.');
    await loadLeads();
    showNotice('Lead updated.');
  } catch (e) {
    alert('Could not update lead: ' + e);
  }
}

async function deleteLead(id) {
  try {
    const check = await fetch('/api/leads/' + id + '/deletion-check');
    const preview = await check.json();
    if (!check.ok) throw new Error(preview.detail || 'Could not check this enquiry.');
    if (!preview.can_delete) { alert(preview.reason); return; }
    const visits = Number(preview.site_visit_count) || 0;
    const visitText = visits ? ` and its ${visits} linked site visit${visits === 1 ? '' : 's'}` : '';
    const contactText = preview.customer_contact_will_be_deleted ?
      ' The contact created with it will also be removed.' : '';
    if (!confirm(`Delete this enquiry${visitText}?${contactText} This cannot be undone.`)) return;
    const res = await fetch('/api/leads/' + id + '?confirm_visits=' + visits, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not delete lead.');
    await Promise.all([loadLeads(), loadDashboard()]);
    showNotice(`Enquiry${visits ? ' and linked site visit' + (visits === 1 ? '' : 's') : ''} deleted.`);
  } catch (e) {
    alert('Could not delete enquiry: ' + e.message);
  }
}


async function loadIntelligence() {
  try {
    const res = await fetch("/api/intelligence");
    if (!res.ok) throw new Error();
    const data = await res.json();

    const jobs = data.jobs || [];
    document.getElementById("jobIntelligenceList").innerHTML = jobs.length ? jobs.map(j => `
      <div class="history-item">
        <strong>${escapeHtml(j.quote_type || "Unknown")}</strong><br>
        Quotes: ${j.count || 0}<br>
        Avg labour: ${pounds(j.avg_labour || 0)} · Avg materials: ${pounds(j.avg_materials || 0)} · Avg total: ${pounds(j.avg_total || 0)}<br>
        Avg profit: ${pounds(j.avg_profit || 0)} · Avg margin: ${Number(j.avg_margin || 0).toFixed(1)}%
      </div>
    `).join("") : "No quote intelligence yet.";

    const materials = data.materials || [];
    document.getElementById("materialIntelligenceList").innerHTML = materials.length ? materials.map(m => `
      <div class="history-item">
        <strong>${escapeHtml(m.name || "Material")}</strong><br>
        ${escapeHtml(m.supplier || "")} · Checks: ${m.checks || 0}<br>
        Avg: ${pounds(m.avg_price || 0)} · Low: ${pounds(m.min_price || 0)} · High: ${pounds(m.max_price || 0)}<br>
        Last checked: ${escapeHtml(formatMaterialDate(m.last_checked || ""))}
      </div>
    `).join("") : "No material price history yet.";
  } catch (e) {
    document.getElementById("jobIntelligenceList").innerHTML = "Unable to load intelligence.";
  }
}

function formatMaterialDate(value) {
  if (!value) return "";
  try {
    const d = new Date(value);
    if (!isNaN(d.getTime())) return d.toLocaleString();
  } catch (e) {}
  return value;
}

async function loadMaterialDb() {
  try {
    const res = await fetch("/api/material-prices");
    if (!res.ok) throw new Error();
    SAVED_MATERIAL_DB = await res.json();

    const suppliers = [...new Set(SAVED_MATERIAL_DB.map(x => x.supplier || "").filter(Boolean))].sort();
    const supplierSelect = document.getElementById("materialDbSupplier");
    if (supplierSelect) {
      const current = supplierSelect.value;
      supplierSelect.innerHTML = '<option value="">All suppliers</option>' + suppliers.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
      supplierSelect.value = current;
    }

    renderMaterialDbList();
  } catch (e) {
    const box = document.getElementById("materialDbList");
    if (box) box.innerHTML = "Unable to load material database.";
  }
}

function renderMaterialDbList() {
  const box = document.getElementById("materialDbList");
  const summary = document.getElementById("materialDbSummary");
  if (!box) return;

  const q = (document.getElementById("materialDbSearch")?.value || "").trim().toLowerCase();
  const supplier = document.getElementById("materialDbSupplier")?.value || "";

  let rows = SAVED_MATERIAL_DB.filter(item => {
    const hay = `${item.name || ""} ${item.supplier || ""} ${item.url || ""}`.toLowerCase();
    const supplierOk = !supplier || (item.supplier || "") === supplier;
    return supplierOk && (!q || hay.includes(q));
  });

  if (summary) summary.innerText = `${rows.length} shown / ${SAVED_MATERIAL_DB.length} saved materials`;

  if (!rows.length) {
    box.innerHTML = "No saved materials found yet. Add product URLs to a quote first, then generate the quote.";
    return;
  }

  box.innerHTML = rows.map(item => {
    const price = item.last_live_price || item.last_price || item.last_manual_price || 0;
    const status = item.last_status || "unknown";
    const badge = status === "live"
      ? '<span class="badge green">live</span>'
      : (status === "cached" ? '<span class="badge green">cached live</span>' : '<span class="badge">manual</span>');

    return `
      <div class="history-item">
        <div><strong>${escapeHtml(item.name || "Unnamed material")}</strong> ${badge}</div>
        <div class="small">${escapeHtml(item.supplier || "")}</div>
        <div style="font-size:22px;font-weight:800;margin:6px 0;">${pounds(price)}</div>
        <div class="small">Times used: ${item.times_used || 0}</div>
        <div class="small">Last checked: ${escapeHtml(formatMaterialDate(item.last_checked_at || ""))}</div>
        <div class="small">Last live success: ${escapeHtml(formatMaterialDate(item.last_success_at || ""))}</div>
        <div class="small" style="word-break:break-all;">${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank">${escapeHtml(item.url)}</a>` : ""}</div>

        <details style="margin-top:10px;">
          <summary>Edit material</summary>
          <label>Name</label>
          <input id="mat_name_${item.id}" value="${escapeHtml(item.name || "")}">
          <label>Supplier</label>
          <input id="mat_supplier_${item.id}" value="${escapeHtml(item.supplier || "")}">
          <label>Product URL</label>
          <input id="mat_url_${item.id}" value="${escapeHtml(item.url || "")}">
          <label>Manual fallback price (£)</label>
          <input id="mat_manual_${item.id}" type="number" step="0.01" value="${Number(item.last_manual_price || item.last_price || 0).toFixed(2)}">
          <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
            <button type="button" class="btn-primary" onclick="saveMaterialDbItem(${item.id})">Save</button>
            <button type="button" class="btn-red" onclick="deleteMaterialDbItem(${item.id})">Delete</button>
          </div>
        </details>
      </div>
    `;
  }).join("");
}

async function saveMaterialDbItem(id) {
  try {
    const payload = {
      name: document.getElementById("mat_name_" + id).value,
      supplier: document.getElementById("mat_supplier_" + id).value,
      url: document.getElementById("mat_url_" + id).value,
      manual_price: parseFloat(document.getElementById("mat_manual_" + id).value || 0),
    };
    const res = await fetch("/api/material-prices/" + id, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error();
    await loadMaterialDb();
    showNotice("Material updated.");
  } catch (e) {
    alert("Could not update material.");
  }
}

async function deleteMaterialDbItem(id) {
  if (!confirm("Delete this material from the database?")) return;
  try {
    const res = await fetch("/api/material-prices/" + id, { method: "DELETE" });
    if (!res.ok) throw new Error();
    await loadMaterialDb();
    showNotice("Material deleted.");
  } catch (e) {
    alert("Could not delete material.");
  }
}

async function refreshMaterialDbPrices() {
  try {
    showNotice("Refreshing material prices...");
    const res = await fetch("/api/material-prices/refresh", { method: "POST" });
    if (!res.ok) throw new Error();
    await loadMaterialDb();
    showNotice("Material prices refreshed.");
  } catch (e) {
    alert("Could not refresh live prices.");
  }
}



async function loadSafety() {
  const statusBox = document.getElementById("safetyStatus");
  const backupBox = document.getElementById("backupList");
  if (!statusBox || !backupBox) return;

  try {
    const res = await fetch("/api/backups");
    if (!res.ok) throw new Error();
    const data = await res.json();
    const counts = data.counts || {};

    statusBox.innerHTML = `
      <strong>App version:</strong> ${escapeHtml(data.version || "-")}<br>
      <strong>Customers:</strong> ${counts.customers ?? "-"}<br>
      <strong>Quotes:</strong> ${counts.quotes ?? "-"}<br>
      <strong>Invoices:</strong> ${counts.invoices ?? "-"}<br>
      <strong>Leads:</strong> ${counts.leads ?? "-"}<br>
      <strong>Saved materials:</strong> ${counts.material_price_cache ?? "-"}<br>
      <strong>Backups:</strong> ${(data.backups || []).length}
    `;

    const backups = data.backups || [];
    backupBox.innerHTML = backups.length ? backups.map(b => `
      <div class="history-item">
        <div><strong>${escapeHtml(b.filename)}</strong></div>
        <div>${Number((b.size_bytes || 0) / 1024).toFixed(1)} KB</div>
        <div>${escapeHtml(b.created_at || "")}</div>
        <div class="history-actions">
          <a class="btn-link btn-light" href="/api/backups/${encodeURIComponent(b.filename)}" target="_blank">Download Backup</a>
        </div>
      </div>
    `).join("") : "No backups yet.";
  } catch (e) {
    statusBox.innerHTML = "Could not load safety status.";
    backupBox.innerHTML = "";
  }
}

async function createBackupNow() {
  try {
    const res = await fetch("/api/backups", { method: "POST" });
    if (!res.ok) throw new Error();
    await loadSafety();
    showNotice("Backup created.");
  } catch (e) {
    alert("Could not create backup.");
  }
}


async function loadCustomers() {
  try {
    const res = await fetch("/api/customers");
    const data = await res.json();
    SAVED_CUSTOMERS = data;
    const box = document.getElementById("customerList");
    const q = (document.getElementById("customerSearch")?.value || "").trim().toLowerCase();
    const filtered = data.filter(c => {
      const hay = `${c.name || ""} ${c.phone || ""} ${c.address || ""}`.toLowerCase();
      return !q || hay.includes(q);
    });

    if (!filtered.length) {
      box.innerHTML = q ? "No matching customers." : "No customers yet.";
      return;
    }

    box.innerHTML = filtered.map(c => `
      <div class="history-item">
        <div><strong>${escapeHtml(c.name || "No customer name")}</strong></div>
        <div>${escapeHtml(c.phone || "")}</div>
        <div class="small">${escapeHtml(c.address || "")}</div>
        <div class="history-actions" style="grid-template-columns:1fr 1fr;">
          <button type="button" class="btn-light" onclick="viewCustomerHistory(${c.id})">View History</button>
          <button type="button" class="btn-light" onclick="startQuoteForCustomer(${c.id})">Start Quote</button>
        </div>
        <div class="history-actions">
          <button type="button" class="btn-red" onclick="deleteCustomer(${c.id})">Delete Customer</button>
        </div>
        <div id="customer_history_${c.id}" class="small" style="margin-top:10px;"></div>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("customerList").innerHTML = "Unable to load customers.";
  }
}

async function viewCustomerHistory(id) {
  try {
    const res = await fetch("/api/customers/" + id + "/history");
    const data = await res.json();
    const box = document.getElementById("customer_history_" + id);

    const quotes = data.quotes || [];
    const invoices = data.invoices || [];

    const quoteRows = quotes.length
      ? quotes.slice(0,10).map(q => `
          <div class="history-item" style="margin-top:10px;padding:10px;background:#fff;">
            <div><strong>${escapeHtml(q.created_at || "")}</strong> — ${pounds(q.total_price || 0)}</div>
            <div>${escapeHtml(q.job || "")}</div>
            <div class="history-actions" style="grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px;">
              <button type="button" class="btn-light" onclick="loadSavedQuote(${q.id})">Open</button>
              <button type="button" class="btn-light" onclick="editSavedQuote(${q.id})">Edit</button>
              <button type="button" class="btn-green" onclick="sendSavedQuoteWhatsApp(${q.id})">WhatsApp</button>
              <button type="button" class="btn-primary" onclick="convertQuoteToInvoice(${q.id})">Invoice</button>
            </div>
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
              <button type="button" class="btn-light" onclick="printSavedQuote(${q.id})">Print / PDF</button>
              <button type="button" class="btn-red" onclick="deleteSavedQuote(${q.id}); setTimeout(() => viewCustomerHistory(${id}), 500);">Delete Quote</button>
            </div>
          </div>
        `).join("")
      : "<div>None</div>";

    const invoiceRows = invoices.length
      ? invoices.slice(0,10).map(i => `
          <div class="history-item" style="margin-top:10px;padding:10px;background:#fff;">
            <div><strong>${escapeHtml(i.invoice_number || "")}</strong> — ${pounds(i.total_price || 0)} — ${escapeHtml(i.status || "")}</div>
            <div class="history-actions" style="grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px;">
              <button type="button" class="btn-light" onclick="openInvoice(${i.id})">Preview Invoice</button>
              <button type="button" class="btn-light" onclick="editInvoice(${i.id})">Edit</button>
              <button type="button" class="btn-primary" onclick="window.open('/invoice/${i.id}', '_blank')">Public Link</button>
            </div>
          </div>
        `).join("")
      : "<div>None</div>";

    box.innerHTML = `
      <div><strong>Quotes:</strong> ${quotes.length}</div>
      ${quoteRows}
      <div style="margin-top:12px;"><strong>Invoices:</strong> ${invoices.length}</div>
      ${invoiceRows}
    `;
  } catch (e) {
    alert("Could not load customer history.");
  }
}

function startQuoteForCustomer(id) {
  const c = SAVED_CUSTOMERS.find(x => x.id === id);
  if (!c) return;
  resetQuoteFormState();
  showTab("quotesTab");
  document.getElementById("customer_name").value = c.name || "";
  document.getElementById("customer_address").value = c.address || "";
  document.getElementById("customer_phone").value = c.phone || "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function startNewQuote() {
  resetQuoteFormState();
  document.getElementById("quote_source").value = "";
  document.getElementById("quote_work_type").value = "";
  b7SetAdditional('quoteAdditional', [], '');
  document.getElementById('customer_email').value = '';
  CURRENT_QUOTE_DATA = null;
  document.getElementById("resultCard").style.display = "none";
  document.getElementById("invoiceCard").style.display = "none";
  document.getElementById("quote_type").value = "small";
  document.getElementById("customer_name").value = "";
  document.getElementById("customer_address").value = "";
  document.getElementById("customer_phone").value = "";
  document.getElementById("job").value = "";
  document.getElementById("labour").value = "";
  document.getElementById("include_materials_handling").checked = true;
  document.getElementById("materials_handling_percent").value = "25";
  document.getElementById("tiling").checked = false;
  document.getElementById("wall_tiling_m2").value = "";
  document.getElementById("floor_tiling_m2").value = "";
  document.getElementById("wall_height").value = "half";
  document.getElementById("customer_supplies_tiles").checked = false;
  document.getElementById("deposit_percent").value = "0";
  clearMaterials();
  const materialSearchPanel = document.getElementById("manualMaterialSearchPanel");
  if (materialSearchPanel) materialSearchPanel.style.display = "none";
  const materialSearchInput = document.getElementById("materialSearch");
  if (materialSearchInput) materialSearchInput.value = "";
  const materialSearchResults = document.getElementById("searchResults");
  if (materialSearchResults) {
    materialSearchResults.innerHTML = "";
    materialSearchResults.classList.add("hidden");
  }
  toggleBathroomFields();
  updateLabourSuggestion();
  showTab("quotesTab");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadSavedQuote(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    document.getElementById('quoteWorkflow').innerText = `Quote #${data.id}: ${data.status.toUpperCase()}${data.next_follow_up ? ' · Follow up ' + data.next_follow_up : ''}${data.loss_reason ? ' · ' + data.loss_reason : ''}. Change outcome in Saved Quotes below.`;
    fillFormFromRequest(data.request, data.id);
    renderQuoteResult(data.result);
    showTab("quotesTab");
    window.scrollTo({ top: 0, behavior: "smooth" });
    showNotice("Quote opened.");
  } catch (e) {
    alert("Could not load saved quote.");
  }
}

async function editSavedQuote(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    document.getElementById('quoteWorkflow').innerText = `Quote #${data.id}: ${data.status.toUpperCase()}${data.next_follow_up ? ' · Follow up ' + data.next_follow_up : ''}. Change outcome in Saved Quotes below.`;

    const q = normaliseQuoteDataForEditing(data);
    fillFormFromRequest(q, data.id || id);

    if (data.result) {
      renderQuoteResult(data.result);
    }

    showTab("quotesTab");
    window.scrollTo({ top: 0, behavior: "smooth" });
    showNotice("Quote loaded for editing.");
  } catch (e) {
    console.error("Edit quote failed", e);
    alert("Could not load quote for editing: " + e.message);
  }
}

async function sendSavedQuoteWhatsApp(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    fillFormFromRequest(data.request, data.id);
    renderQuoteResult(data.result);
    showTab("quotesTab");
    setTimeout(() => document.getElementById("whatsappBtn").click(), 250);
  } catch (e) {
    alert("Could not open WhatsApp for this quote.");
  }
}

async function printSavedQuote(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    fillFormFromRequest(data.request, data.id);
    renderQuoteResult(data.result);
    showTab("quotesTab");
    setTimeout(() => window.print(), 250);
  } catch (e) {
    alert("Could not print this quote.");
  }
}

async function deleteSavedQuote(id) {
  if (!confirm("Delete this saved quote?")) return;
  try {
    const res = await fetch("/api/quotes/" + id, { method: "DELETE" });
    if (!res.ok) throw new Error();
    await loadHistory();
    await loadCustomers();
    await loadDashboard();
    showNotice("Saved quote deleted.");
  } catch (e) {
    alert("Could not delete saved quote.");
  }
}


let LAST_AI_QUOTE_DRAFT = null;
let AI_QUOTE_DRAFT_PENDING = false;

function clearAIQuoteDraftState() {
  LAST_AI_QUOTE_DRAFT = null;
  AI_QUOTE_DRAFT_PENDING = false;
  const box = document.getElementById("aiQuoteResult");
  if (box) box.innerHTML = "";
}

async function checkAIQuoteStatus() {
  const status = document.getElementById("aiQuoteStatus");
  if (!status) return;

  try {
    const res = await fetch("/api/ai-quote-status");
    const data = await res.json();
    if (data.configured) {
      status.innerHTML = `AI connected · model: ${escapeHtml(data.model || "")}`;
    } else {
      status.innerHTML = `<strong>Setup needed:</strong> add OPENAI_API_KEY in Render environment settings.`;
    }
  } catch (e) {
    status.innerHTML = "Could not check AI connection.";
  }
}


let CURRENT_SITE_SURVEY = null;
let RECORDED_SITE_AUDIO = null;
let SITE_AUDIO_RECORDER = null;
let SITE_AUDIO_STREAM = null;
let SITE_AUDIO_CHUNKS = [];
let SITE_AUDIO_TIMER = null;
let SITE_AUDIO_STARTED_AT = 0;
let CAPTURED_SITE_PHOTOS = [];
let RECORDED_SITE_VIDEO = null;
let SITE_MEDIA_RECORDER = null;
let SITE_CAMERA_STREAM = null;
let SITE_VIDEO_CHUNKS = [];
let SITE_RECORDING_TIMER = null;
let SITE_RECORDING_STARTED_AT = 0;
let SITE_SURVEY_ATTACHED = false;


function toggleSiteInformationPanel() {
  document.getElementById("siteInformationPanel")?.classList.toggle("hidden");
}

function preferredAudioMimeType() {
  if (!window.MediaRecorder) return "";
  const options = [
    "audio/mp4",
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus"
  ];
  return options.find(type => MediaRecorder.isTypeSupported(type)) || "";
}

async function startSiteAudioRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    document.getElementById("siteAudioFallback")?.click();
    return;
  }

  try {
    SITE_AUDIO_STREAM = await navigator.mediaDevices.getUserMedia({audio: true});
    SITE_AUDIO_CHUNKS = [];
    const mimeType = preferredAudioMimeType();
    const options = {audioBitsPerSecond: 48000};
    if (mimeType) options.mimeType = mimeType;

    SITE_AUDIO_RECORDER = new MediaRecorder(SITE_AUDIO_STREAM, options);
    SITE_AUDIO_RECORDER.ondataavailable = event => {
      if (event.data && event.data.size) SITE_AUDIO_CHUNKS.push(event.data);
      const bytes = SITE_AUDIO_CHUNKS.reduce((sum, item) => sum + item.size, 0);
      document.getElementById("siteAudioSize").innerText = `Recorded ${formatMediaBytes(bytes)}`;
    };
    SITE_AUDIO_RECORDER.onstop = finishSiteAudioRecording;
    SITE_AUDIO_RECORDER.start(1000);

    SITE_AUDIO_STARTED_AT = Date.now();
    document.getElementById("siteAudioRecorder")?.classList.remove("hidden");
    document.getElementById("recordSiteAudioButton").disabled = true;

    SITE_AUDIO_TIMER = setInterval(() => {
      const seconds = Math.floor((Date.now() - SITE_AUDIO_STARTED_AT) / 1000);
      document.getElementById("siteAudioTimer").innerText =
        `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
      if (seconds >= 300) stopSiteAudioRecording();
    }, 250);
  } catch (error) {
    document.getElementById("siteAudioFallback")?.click();
  }
}

function stopSiteAudioRecording() {
  if (SITE_AUDIO_RECORDER && SITE_AUDIO_RECORDER.state !== "inactive") {
    SITE_AUDIO_RECORDER.stop();
  }
}

function finishSiteAudioRecording() {
  const mimeType = SITE_AUDIO_RECORDER?.mimeType || "audio/webm";
  const extension = mimeType.includes("mp4") ? "m4a" : mimeType.includes("ogg") ? "ogg" : "webm";
  const blob = new Blob(SITE_AUDIO_CHUNKS, {type: mimeType});
  RECORDED_SITE_AUDIO = new File(
    [blob],
    `job-walkthrough-${Date.now()}.${extension}`,
    {type: mimeType, lastModified: Date.now()}
  );
  cleanupSiteAudioRecorder();
  updateSiteCaptureSummary();
  document.getElementById("siteSurveyStatus").innerHTML =
    `Audio walkthrough recorded (${formatMediaBytes(RECORDED_SITE_AUDIO.size)}). Press Analyse Site Visit.`;
}

function cancelSiteAudioRecording() {
  SITE_AUDIO_CHUNKS = [];
  RECORDED_SITE_AUDIO = null;
  cleanupSiteAudioRecorder();
  updateSiteCaptureSummary();
}

function cleanupSiteAudioRecorder() {
  if (SITE_AUDIO_TIMER) clearInterval(SITE_AUDIO_TIMER);
  SITE_AUDIO_TIMER = null;
  if (SITE_AUDIO_STREAM) SITE_AUDIO_STREAM.getTracks().forEach(track => track.stop());
  SITE_AUDIO_STREAM = null;
  document.getElementById("siteAudioRecorder")?.classList.add("hidden");
  const button = document.getElementById("recordSiteAudioButton");
  if (button) button.disabled = false;
  const timer = document.getElementById("siteAudioTimer");
  if (timer) timer.innerText = "00:00";
}

function formatMediaBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function updateSiteCaptureSummary() {
  const existingPhotos = [...(document.getElementById("siteSurveyPhotos")?.files || [])];
  const existingVideo = document.getElementById("siteSurveyVideo")?.files?.[0];
  const existingAudio = document.getElementById("siteSurveyAudio")?.files?.[0];
  const plans = [...(document.getElementById("sitePlans")?.files || [])];
  const notes = String(document.getElementById("siteVisitNotes")?.value || "").trim();

  const photoCount = CAPTURED_SITE_PHOTOS.length + existingPhotos.length;
  const video = RECORDED_SITE_VIDEO || existingVideo;
  const audio = RECORDED_SITE_AUDIO || existingAudio;
  const parts = [];

  if (audio) parts.push(`audio ${formatMediaBytes(audio.size)}`);
  if (video) parts.push(`video ${formatMediaBytes(video.size)}`);
  if (photoCount) parts.push(`${photoCount} photo${photoCount === 1 ? "" : "s"}`);
  if (plans.length) parts.push(`${plans.length} plan${plans.length === 1 ? "" : "s"}`);
  if (notes) parts.push("notes");

  document.getElementById("siteCaptureSummary").innerHTML =
    parts.length ? `Ready: ${parts.join(" · ")}` : "No site information added yet.";
}

function takeSitePhoto() {
  document.getElementById("siteCameraPhoto")?.click();
}

function preferredRecorderMimeType() {
  if (!window.MediaRecorder) return "";
  const options = [
    "video/mp4;codecs=h264,aac",
    "video/mp4",
    "video/webm;codecs=vp8,opus",
    "video/webm"
  ];
  return options.find(type => MediaRecorder.isTypeSupported(type)) || "";
}

async function startSiteVideoRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    document.getElementById("siteCameraVideoFallback")?.click();
    return;
  }

  try {
    SITE_CAMERA_STREAM = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: {ideal: "environment"},
        width: {ideal: 1280, max: 1280},
        height: {ideal: 720, max: 720},
        frameRate: {ideal: 24, max: 30}
      },
      audio: true
    });

    const preview = document.getElementById("siteVideoPreview");
    preview.srcObject = SITE_CAMERA_STREAM;
    document.getElementById("siteVideoRecorder").classList.remove("hidden");

    SITE_VIDEO_CHUNKS = [];
    const mimeType = preferredRecorderMimeType();
    const options = {
      videoBitsPerSecond: 900000,
      audioBitsPerSecond: 48000
    };
    if (mimeType) options.mimeType = mimeType;

    SITE_MEDIA_RECORDER = new MediaRecorder(SITE_CAMERA_STREAM, options);
    SITE_MEDIA_RECORDER.ondataavailable = event => {
      if (event.data && event.data.size) SITE_VIDEO_CHUNKS.push(event.data);
      const bytes = SITE_VIDEO_CHUNKS.reduce((sum, item) => sum + item.size, 0);
      document.getElementById("siteVideoSize").innerText = `Recorded ${formatMediaBytes(bytes)}`;
    };
    SITE_MEDIA_RECORDER.onstop = finishSiteVideoRecording;
    SITE_MEDIA_RECORDER.start(1000);

    SITE_RECORDING_STARTED_AT = Date.now();
    document.getElementById("recordSiteVideoButton").disabled = true;
    SITE_RECORDING_TIMER = setInterval(() => {
      const seconds = Math.floor((Date.now() - SITE_RECORDING_STARTED_AT) / 1000);
      const minutes = Math.floor(seconds / 60);
      const remainder = seconds % 60;
      document.getElementById("siteVideoTimer").innerText =
        `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
      if (seconds >= 90) stopSiteVideoRecording();
    }, 250);
  } catch (error) {
    document.getElementById("siteCameraVideoFallback")?.click();
  }
}

function stopSiteVideoRecording() {
  if (SITE_MEDIA_RECORDER && SITE_MEDIA_RECORDER.state !== "inactive") {
    SITE_MEDIA_RECORDER.stop();
  }
}

function cancelSiteVideoRecording() {
  SITE_VIDEO_CHUNKS = [];
  RECORDED_SITE_VIDEO = null;
  cleanupSiteRecorder();
  updateSiteCaptureSummary();
}

function finishSiteVideoRecording() {
  const mimeType = SITE_MEDIA_RECORDER?.mimeType || "video/webm";
  const extension = mimeType.includes("mp4") ? "mp4" : "webm";
  const blob = new Blob(SITE_VIDEO_CHUNKS, {type: mimeType});
  RECORDED_SITE_VIDEO = new File(
    [blob],
    `site-survey-${Date.now()}.${extension}`,
    {type: mimeType, lastModified: Date.now()}
  );
  cleanupSiteRecorder();
  updateSiteCaptureSummary();
  document.getElementById("siteSurveyStatus").innerHTML =
    `Video recorded (${formatMediaBytes(RECORDED_SITE_VIDEO.size)}). Press Analyse captured media.`;
}

function cleanupSiteRecorder() {
  if (SITE_RECORDING_TIMER) clearInterval(SITE_RECORDING_TIMER);
  SITE_RECORDING_TIMER = null;
  if (SITE_CAMERA_STREAM) {
    SITE_CAMERA_STREAM.getTracks().forEach(track => track.stop());
  }
  SITE_CAMERA_STREAM = null;
  const preview = document.getElementById("siteVideoPreview");
  if (preview) preview.srcObject = null;
  document.getElementById("siteVideoRecorder")?.classList.add("hidden");
  const button = document.getElementById("recordSiteVideoButton");
  if (button) button.disabled = false;
  document.getElementById("siteVideoTimer").innerText = "00:00";
}

document.getElementById("siteCameraPhoto")?.addEventListener("change", event => {
  const file = event.target.files?.[0];
  if (file) {
    if (CAPTURED_SITE_PHOTOS.length >= 6) {
      alert("You can use up to 6 site photos.");
    } else {
      CAPTURED_SITE_PHOTOS.push(file);
      CURRENT_SITE_SURVEY = null;
      SITE_SURVEY_ATTACHED = false;
    }
  }
  event.target.value = "";
  updateSiteCaptureSummary();
});

document.getElementById("siteCameraVideoFallback")?.addEventListener("change", event => {
  const file = event.target.files?.[0];
  if (file) {
    RECORDED_SITE_VIDEO = file;
    CURRENT_SITE_SURVEY = null;
    SITE_SURVEY_ATTACHED = false;
  }
  event.target.value = "";
  updateSiteCaptureSummary();
});

document.getElementById("siteSurveyPhotos")?.addEventListener("change", updateSiteCaptureSummary);
document.getElementById("siteSurveyVideo")?.addEventListener("change", updateSiteCaptureSummary);
document.getElementById("siteSurveyAudio")?.addEventListener("change", updateSiteCaptureSummary);
document.getElementById("sitePlans")?.addEventListener("change", updateSiteCaptureSummary);
document.getElementById("siteVisitNotes")?.addEventListener("input", updateSiteCaptureSummary);
document.getElementById("siteAudioFallback")?.addEventListener("change", event => {
  const file = event.target.files?.[0];
  if (file) RECORDED_SITE_AUDIO = file;
  event.target.value = "";
  updateSiteCaptureSummary();
});

function surveyStatusLabel(value) {
  return ({
    confirmed_visible: "Confirmed visible",
    not_visible: "Not visible",
    present_condition_unconfirmed: "Present — condition unconfirmed",
    confirmed_by_nigel: "Confirmed by Nigel",
    ai_inferred: "AI inferred"
  })[value] || value || "Unknown";
}

function surveyActionLabel(value) {
  return ({
    reuse_existing: "Reuse existing",
    keep_optional: "Keep optional",
    include_required: "Include required",
    site_check: "Site check",
    no_quote_change: "No quote change"
  })[value] || value || "";
}

async function analyseSiteSurvey() {
  const chosenPhotos = [...(document.getElementById("siteSurveyPhotos")?.files || [])];
  const photos = [...CAPTURED_SITE_PHOTOS, ...chosenPhotos];
  const chosenVideo = document.getElementById("siteSurveyVideo")?.files?.[0];
  const video = RECORDED_SITE_VIDEO || chosenVideo;
  const chosenAudio = document.getElementById("siteSurveyAudio")?.files?.[0];
  const audio = RECORDED_SITE_AUDIO || chosenAudio;
  const plans = [...(document.getElementById("sitePlans")?.files || [])];
  const siteNotes = document.getElementById("siteVisitNotes")?.value || "";
  const status = document.getElementById("siteSurveyStatus");

  if (!photos.length && !video && !audio && !plans.length && !siteNotes.trim()) {
    alert("Record a job walkthrough, or add video, photos, plans or notes.");
    return;
  }
  if (photos.length > 6) {
    alert("V12.4 analyses up to 6 photos at a time.");
    return;
  }
  const oversizedPhoto = photos.find(file => file.size > 10 * 1024 * 1024);
  if (oversizedPhoto) {
    alert(`${oversizedPhoto.name} is over the 10 MB photo limit.`);
    return;
  }
  if (video && video.size > 80 * 1024 * 1024) {
    alert("This video is over 80 MB. Use the in-app recorder or record a shorter video.");
    return;
  }
  if (audio && audio.size > 40 * 1024 * 1024) {
    alert("Keep the audio walkthrough below 40 MB.");
    return;
  }

  const form = new FormData();
  form.append("job_description", document.getElementById("job")?.value || "");
  form.append("site_notes", siteNotes);
  photos.forEach(file => form.append("photos", file));
  plans.forEach(file => form.append("plans", file));
  if (video) form.append("video", video);
  if (audio) form.append("audio", audio);

  status.innerHTML = "Analysing the walkthrough, transcript, visual evidence, plans and notes…";
  document.getElementById("siteSurveyResult").innerHTML = "";
  SITE_SURVEY_ATTACHED = false;

  try {
    const response = await fetch("/api/site-survey", {method: "POST", body: form});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Site survey failed.");

    CURRENT_SITE_SURVEY = data;
    SITE_SURVEY_ATTACHED = true;

    const jobField = document.getElementById("job");
    if (jobField && !String(jobField.value || "").trim()) {
      jobField.value = data.proposed_job_description || data.summary || "";
      jobField.dispatchEvent(new Event("input", {bubbles: true}));
      CURRENT_SITE_SURVEY.merged_job_description = jobField.value;
      CURRENT_SITE_SURVEY.description_merge_mode = "created";
    }

    renderSiteSurvey(data);
    status.innerHTML =
      `✓ Site visit analysed and attached · ${(data.input_modes || []).join(", ") || "notes"} used.`;
    showNotice("Site visit analysed. Building the quote next…");
    return true;
  } catch (error) {
    CURRENT_SITE_SURVEY = null;
    SITE_SURVEY_ATTACHED = false;
    status.innerHTML =
      `<span style="color:#b91c1c;">${escapeHtml(error.message || "Site survey failed.")}</span>`;
    return false;
  }
}

async function analyseAndBuildQuote() {
  const button = document.getElementById("aiQuoteButton");
  const hasSiteInfo = Boolean(
    CAPTURED_SITE_PHOTOS.length || RECORDED_SITE_VIDEO || RECORDED_SITE_AUDIO ||
    document.getElementById("siteSurveyPhotos")?.files?.length ||
    document.getElementById("siteSurveyVideo")?.files?.length ||
    document.getElementById("siteSurveyAudio")?.files?.length ||
    document.getElementById("sitePlans")?.files?.length ||
    document.getElementById("siteVisitNotes")?.value?.trim()
  );
  if (button) { button.disabled = true; button.innerText = "Working…"; }
  try {
    if (hasSiteInfo) {
      const ok = await analyseSiteSurvey();
      if (!ok) return;
    }
    await generateAIQuoteDraft();
  } finally {
    if (button) { button.disabled = false; button.innerText = "✨ Analyse Site & Build Quote"; }
  }
}


function normaliseDescriptionText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .replace(/\s+([.,;:])/g, "$1")
    .trim();
}

function descriptionSentenceKeys(value) {
  return normaliseDescriptionText(value)
    .split(/(?<=[.!?])\s+/)
    .map(sentence => sentence.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim())
    .filter(Boolean);
}

function mergeSurveyDescription(existingText, additionText) {
  const existing = String(existingText || "").trim();
  const addition = String(additionText || "").trim();
  if (!existing) return addition;
  if (!addition) return existing;

  const existingKeys = descriptionSentenceKeys(existing);
  const newSentences = addition
    .split(/(?<=[.!?])\s+/)
    .map(sentence => sentence.trim())
    .filter(Boolean)
    .filter(sentence => {
      const key = sentence.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();
      if (!key) return false;
      return !existingKeys.some(existingKey =>
        existingKey === key ||
        existingKey.includes(key) ||
        key.includes(existingKey)
      );
    });

  if (!newSentences.length) return existing;
  return `${existing}\n\nSite visit findings:\n${newSentences.join(" ")}`.trim();
}

function applySurveyDescription(mode = "append") {
  if (!CURRENT_SITE_SURVEY) {
    alert("Analyse the site media first.");
    return;
  }

  const jobField = document.getElementById("job");
  if (!jobField) return;

  const existing = jobField.value || "";
  const completeDescription =
    CURRENT_SITE_SURVEY.proposed_job_description ||
    CURRENT_SITE_SURVEY.summary ||
    "";
  const addition =
    CURRENT_SITE_SURVEY.site_visit_addition ||
    CURRENT_SITE_SURVEY.summary ||
    "";

  if (mode === "replace" || !existing.trim()) {
    jobField.value = completeDescription;
  } else {
    jobField.value = mergeSurveyDescription(existing, addition);
  }

  jobField.dispatchEvent(new Event("input", {bubbles: true}));
  CURRENT_SITE_SURVEY.merged_job_description = jobField.value;
  CURRENT_SITE_SURVEY.description_merge_mode =
    existing.trim() && mode !== "replace" ? "appended" : "created";

  const mergeStatus = document.getElementById("surveyDescriptionStatus");
  if (mergeStatus) {
    mergeStatus.innerHTML =
      existing.trim() && mode !== "replace"
        ? "✓ New site findings added. Original enquiry preserved."
        : "✓ Job description created from the site survey.";
  }

  showNotice(
    existing.trim() && mode !== "replace"
      ? "Site findings added to the existing job description."
      : "Job description created from the site survey."
  );
}

function surveyDescriptionPreview(data) {
  const jobField = document.getElementById("job");
  const existing = String(jobField?.value || "").trim();
  const completeDescription =
    data.proposed_job_description || data.summary || "";
  const addition = data.site_visit_addition || data.summary || "";
  const preview = existing
    ? mergeSurveyDescription(existing, addition)
    : completeDescription;

  return `
    <div style="margin-top:10px;padding:10px;border:1px solid #7c3aed;border-radius:9px;background:#faf5ff;">
      <strong>${existing ? "Add site findings to existing enquiry" : "Create job description from survey"}</strong>
      <div class="small" style="margin-top:4px;">
        ${existing
          ? "The website enquiry will stay unchanged at the top. Only new site-visit information will be appended."
          : "The survey has enough information to fill the job description box."}
      </div>
      <div style="margin-top:8px;padding:8px;border:1px solid #ddd;border-radius:8px;background:white;white-space:pre-wrap;">${escapeHtml(preview)}</div>
      <div id="surveyDescriptionStatus" class="small" style="margin-top:6px;"></div>
      <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
        <button type="button" class="btn-green" onclick="applySurveyDescription('append')">
          ${existing ? "Add new findings" : "Use this description"}
        </button>
        <button type="button" class="btn-light" onclick="applySurveyDescription('replace')">
          Replace description
        </button>
      </div>
    </div>`;
}

function renderSiteSurvey(data) {
  const box = document.getElementById("siteSurveyResult");
  const components = data.components || [];
  const actions = data.material_actions || [];
  const warnings = data.warnings || [];

  box.innerHTML = `<div class="history-item" style="padding:10px;border-color:#2563eb;">
    <strong>AI site visit summary</strong><br>${escapeHtml(data.summary || "")}
    <div style="margin-top:6px;color:#166534;"><strong>✓ Attached to the next AI quote</strong></div>
    ${surveyDescriptionPreview(data)}
    ${data.transcript ? `<details style="margin-top:7px;"><summary><strong>Walkthrough transcript</strong></summary><div style="margin-top:5px;">${escapeHtml(data.transcript)}</div></details>` : ""}
    ${components.length ? `<div style="margin-top:9px;"><strong>Components reviewed</strong>${components.map(item => `<div style="margin-top:6px;padding:8px;border:1px solid #ddd;border-radius:8px;background:white;"><strong>${escapeHtml(item.component || "")}</strong><br><span class="small">${escapeHtml(surveyStatusLabel(item.status))} · ${Number(item.confidence || 0)}%</span><br>${escapeHtml(item.condition || "")}<br><strong>Quote action:</strong> ${escapeHtml(surveyActionLabel(item.quote_action))}${item.evidence ? `<br><span class="small">${escapeHtml(item.evidence)}</span>` : ""}</div>`).join("")}</div>` : ""}
    ${actions.length ? `<div style="margin-top:9px;"><strong>Material decisions</strong><br>${actions.map(item => `• ${escapeHtml(item.material_name)}: ${escapeHtml(surveyActionLabel(item.action))} — ${escapeHtml(item.reason)} (${Number(item.confidence || 0)}%)`).join("<br>")}</div>` : ""}
    ${warnings.length ? `<div style="margin-top:9px;"><strong>Limitations</strong><br>${warnings.map(item => `△ ${escapeHtml(item)}`).join("<br>")}</div>` : ""}
  </div>`;
}

function useSiteSurveyInQuote() {
  if (!CURRENT_SITE_SURVEY) return alert("Analyse the site media first.");
  SITE_SURVEY_ATTACHED = true;
  document.getElementById("siteSurveyStatus").innerHTML =
    "✓ Survey attached. Press Build Quote with AI.";
  showNotice("Site survey attached to the next AI quote draft.");
}

function clearSiteSurvey() {
  cancelSiteVideoRecording();
  CURRENT_SITE_SURVEY = null;
  SITE_SURVEY_ATTACHED = false;
  CAPTURED_SITE_PHOTOS = [];
  RECORDED_SITE_VIDEO = null;
  RECORDED_SITE_AUDIO = null;

  const photos = document.getElementById("siteSurveyPhotos");
  const video = document.getElementById("siteSurveyVideo");
  const audio = document.getElementById("siteSurveyAudio");
  const plans = document.getElementById("sitePlans");
  const notes = document.getElementById("siteVisitNotes");
  if (photos) photos.value = "";
  if (video) video.value = "";
  if (audio) audio.value = "";
  if (plans) plans.value = "";
  if (notes) notes.value = "";

  document.getElementById("siteSurveyResult").innerHTML = "";
  document.getElementById("siteSurveyStatus").innerHTML = "";
  updateSiteCaptureSummary();
}

function currentMaterialsForAI() {
  return [...document.querySelectorAll("#materials .material-row")].map(row => ({
    name: row.querySelector(".m-name")?.value || "",
    quantity: Number(row.querySelector(".m-qty")?.value || 1),
    supplier: row.querySelector(".m-supplier")?.value || "",
    url: row.querySelector(".m-url")?.value || "",
    manual_price: Number(row.querySelector(".m-manual")?.value || 0)
  })).filter(m => m.name.trim());
}

async function generateAIQuoteDraft() {
  if (!Array.isArray(SAVED_MATERIAL_DB) || !SAVED_MATERIAL_DB.length) {
    try { await loadMaterialDb(); } catch (e) {}
  }
  const button = document.getElementById("aiQuoteButton");
  const status = document.getElementById("aiQuoteStatus");
  const resultBox = document.getElementById("aiQuoteResult");
  let job = document.getElementById("job")?.value || "";

  if (!job.trim() && CURRENT_SITE_SURVEY) {
    applySurveyDescription("replace");
    job = document.getElementById("job")?.value || "";
  }

  if (!job.trim()) {
    alert("Enter the job description first.");
    return;
  }

  if (button) {
    button.disabled = true;
    button.innerText = "Building quote…";
  }
  if (status) {
    status.innerHTML = CURRENT_SITE_SURVEY
      ? "Using the attached site visit, audio transcript, any visual evidence, job history, materials and labour…"
      : "No site survey attached — using the written job description, history, materials and labour only…";
  }
  if (resultBox) resultBox.innerHTML = "";

  const hasUnanalysedMedia =
    CAPTURED_SITE_PHOTOS.length ||
    RECORDED_SITE_VIDEO ||
    document.getElementById("siteSurveyPhotos")?.files?.length ||
    document.getElementById("siteSurveyVideo")?.files?.length;

  if (hasUnanalysedMedia && !CURRENT_SITE_SURVEY) {
    const continueWithoutSurvey = confirm(
      "You have site media selected, but it has not been analysed. Continue without using the photos/video?"
    );
    if (!continueWithoutSurvey) {
      if (button) {
        button.disabled = false;
        button.innerText = "✨ Analyse Site & Build Quote";
      }
      return;
    }
  }

  const payload = {
    job_description: job,
    quote_type: document.getElementById("quote_type")?.value || "small",
    customer_name: document.getElementById("customer_name")?.value || "",
    customer_address: document.getElementById("customer_address")?.value || "",
    current_labour: Number(document.getElementById("labour")?.value || 0),
    current_materials: currentMaterialsForAI(),
    site_survey: CURRENT_SITE_SURVEY
      ? {
          ...CURRENT_SITE_SURVEY,
          merged_job_description: document.getElementById("job")?.value || ""
        }
      : {}
  };

  try {
    const res = await fetch("/api/ai-quote-draft", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Could not generate AI quote draft.");
    }

    LAST_AI_QUOTE_DRAFT = data.draft;
    AI_QUOTE_DRAFT_PENDING = true;
    renderAIQuoteDraft(data);
    if (status) {
      const context = data.context_summary || {};
      status.innerHTML = context.is_multi_job
        ? `Quote health check complete · ${context.multi_job_count || 0} physical job(s) · review any health warnings before applying it.`
        : context.smart_job_type
          ? `Quote health check complete · ${escapeHtml(context.smart_job_type)} · review any health warnings before applying it.`
          : `Estimator dashboard ready using database-first fallback.`;
    }
  } catch (e) {
    if (status) status.innerHTML = `<strong>AI error:</strong> ${escapeHtml(e.message || String(e))}`;
  } finally {
    if (button) {
      button.disabled = false;
      button.innerText = "✨ Analyse Site & Build Quote";
    }
  }
}


function addQuoteHealthSuggestion(suggestionId) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) return;

  const suggestion = (draft.quote_health.missing_items || []).find(item => item.id === suggestionId);
  if (!suggestion) return;

  draft.materials = draft.materials || [];
  const alreadyExists = draft.materials.some(item =>
    canonicalMaterialName(item.name || "") === canonicalMaterialName(suggestion.name || "")
  );

  if (!alreadyExists) {
    draft.materials.push({
      name: suggestion.name || "",
      quantity: Number(suggestion.quantity || 1),
      supplier: suggestion.supplier || "City Plumbing",
      url: suggestion.url || "",
      manual_price: Number(suggestion.manual_price || 0),
      required: !suggestion.optional,
      display_status: suggestion.optional ? "optional" : "required",
      data_source: "quote_health_suggestion",
      reason: suggestion.reason || "",
      include_in_quote: true,
      optional_selected: Boolean(suggestion.optional)
    });
  }

  const selectedMaterial = draft.materials.find(item =>
    canonicalMaterialName(item.name || "") === canonicalMaterialName(suggestion.name || "")
  );
  if (selectedMaterial) {
    selectedMaterial.include_in_quote = true;
    if (suggestion.optional) selectedMaterial.optional_selected = true;
    mergeBundleMaterialIntoForm(selectedMaterial);
    mergeDuplicateMaterialRowsInForm();
  }

  draft.quote_health.missing_items = (draft.quote_health.missing_items || [])
    .filter(item => item.id !== suggestionId);
  draft.quote_health.score = Math.min(100, Number(draft.quote_health.score || 0) + (suggestion.optional ? 4 : 9));
  draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
  draft.quote_health.checks_passed.push(`${suggestion.name} was added for review.`);
  draft.quote_health.readiness = "review_recommended";
  draft.quote_health.readiness_label = "Review recommended";

  renderAIQuoteDraft({draft});
  showNotice(`${suggestion.name} added to the AI draft. Check its supplier and price.`);
}

function ignoreQuoteHealthSuggestion(suggestionId) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) return;

  const suggestion = (draft.quote_health.missing_items || []).find(item => item.id === suggestionId);
  draft.quote_health.missing_items = (draft.quote_health.missing_items || [])
    .filter(item => item.id !== suggestionId);
  draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
  if (suggestion) {
    draft.quote_health.checks_passed.push(`${suggestion.name} was reviewed and ignored.`);
  }

  renderAIQuoteDraft({draft});
  showNotice("Suggestion ignored for this draft.");
}


function useSuggestedQuantity(warningId) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) return;
  const warning = (draft.quote_health.quantity_warnings || []).find(x => x.id === warningId);
  if (!warning || warning.no_auto_fix) return;

  const target = canonicalMaterialName(warning.material || "");
  const matches = (draft.materials || []).filter(item => {
    const current = canonicalMaterialName(item.name || "");
    return current === target || current.includes(target) || target.includes(current);
  });

  if (!matches.length) return;

  matches[0].quantity = Number(warning.suggested_quantity || 1);
  for (let i = 1; i < matches.length; i++) matches[i].quantity = 0;
  draft.materials = (draft.materials || []).filter(item => Number(item.quantity || 0) > 0);
  draft.quote_health.quantity_warnings = (draft.quote_health.quantity_warnings || []).filter(x => x.id !== warningId);
  draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
  draft.quote_health.checks_passed.push(`${warning.material} quantity changed to ${warning.suggested_quantity}.`);
  draft.quote_health.score = Math.min(100, Number(draft.quote_health.score || 0) + 6);

  renderAIQuoteDraft({draft});
  showNotice(`${warning.material} quantity changed to ${warning.suggested_quantity}.`);
}

function keepCurrentQuantity(warningId) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) return;
  const warning = (draft.quote_health.quantity_warnings || []).find(x => x.id === warningId);
  draft.quote_health.quantity_warnings = (draft.quote_health.quantity_warnings || []).filter(x => x.id !== warningId);
  if (warning) {
    draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
    draft.quote_health.checks_passed.push(`${warning.material} quantity reviewed and kept.`);
  }
  renderAIQuoteDraft({draft});
  showNotice("Current quantity kept for this draft.");
}



function bundleMaterialIdentity(name) {
  const raw = String(name || "").toLowerCase();
  const sizes = [...raw.matchAll(/\b(\d{1,3})\s*mm\b/g)]
    .map(match => Number(match[1]))
    .sort((a, b) => a - b);
  const sizeKey = sizes.length ? sizes.join("x") : "";

  if (/\bcopper\b/.test(raw) && /\b(pipe|tube)\b/.test(raw)) {
    return `copper-pipe:${sizeKey || "unknown"}`;
  }
  if (/\bplastic\b/.test(raw) && /\b(pipe|tube)\b/.test(raw)) {
    return `plastic-pipe:${sizeKey || "unknown"}`;
  }
  if (/\bend[\s-]?feed\b/.test(raw) && /\belbow\b|\bbend\b/.test(raw)) {
    return `endfeed-elbow:${sizeKey || "unknown"}`;
  }
  if (/\bend[\s-]?feed\b/.test(raw) && /\btee\b/.test(raw)) {
    return `endfeed-tee:${sizeKey || "unknown"}`;
  }
  if (/\bcoupler\b|\bcoupling\b/.test(raw)) {
    return `coupler:${sizeKey || "unknown"}`;
  }
  return `canonical:${canonicalMaterialName(name || "")}`;
}

function materialValuesScore(material) {
  let score = 0;
  if (String(material?.url || "").trim()) score += 8;
  if (Number(material?.manual_price || material?.live_price || 0) > 0) score += 6;
  if (String(material?.supplier || "").trim()) score += 2;
  if (String(material?.source || "").includes("live")) score += 2;
  return score;
}

function mergePreferredMaterialValues(target, incoming) {
  const targetScore = materialValuesScore(target);
  const incomingScore = materialValuesScore(incoming);

  // Keep the more useful product identity where one row has URL/price data.
  if (incomingScore > targetScore) {
    if (incoming.name) target.name = incoming.name;
    if (incoming.supplier) target.supplier = incoming.supplier;
    if (incoming.url) target.url = incoming.url;
    if (Number(incoming.manual_price || incoming.live_price || 0) > 0) {
      target.manual_price = Number(incoming.manual_price || incoming.live_price || 0);
    }
    if (incoming.source) target.source = incoming.source;
    if (incoming.price_source) target.price_source = incoming.price_source;
    if (incoming.sku) target.sku = incoming.sku;
    if (incoming.image_url) target.image_url = incoming.image_url;
    if (incoming.checked_at) target.checked_at = incoming.checked_at;
  } else {
    if (!target.supplier && incoming.supplier) target.supplier = incoming.supplier;
    if (!target.url && incoming.url) target.url = incoming.url;
    if (!Number(target.manual_price || 0) && Number(incoming.manual_price || incoming.live_price || 0) > 0) {
      target.manual_price = Number(incoming.manual_price || incoming.live_price || 0);
    }
  }

  target.required = Boolean(target.required || incoming.required);
  target.display_status = target.required ? "required" : (target.display_status || incoming.display_status || "optional");
  target.material_confidence = Math.max(
    Number(target.material_confidence || 0),
    Number(incoming.material_confidence || 0)
  );
  return target;
}

function findMaterialRowByCanonicalName(materialName) {
  const targetIdentity = bundleMaterialIdentity(materialName || "");
  return [...document.querySelectorAll("#materials .material-row")].find(row => {
    const existingName = row.querySelector(".m-name")?.value || "";
    return bundleMaterialIdentity(existingName) === targetIdentity;
  }) || null;
}

function mergeBundleMaterialIntoDraft(draft, item) {
  draft.materials = draft.materials || [];
  const targetIdentity = bundleMaterialIdentity(item.name || "");
  let existing = draft.materials.find(material =>
    bundleMaterialIdentity(material.name || "") === targetIdentity
  );

  const incomingQty = Number(item.quantity || 1);
  if (existing) {
    existing.quantity = Math.max(Number(existing.quantity || 0), incomingQty);
    mergePreferredMaterialValues(existing, {
      ...item,
      required: !item.optional,
      display_status: item.optional ? "optional" : "required",
      material_confidence: Number(item.confidence || 75),
      manual_price: Number(item.manual_price || item.live_price || item.price || 0)
    });
    return {material: existing, created: false};
  }

  existing = {
    name: item.name || "",
    quantity: incomingQty,
    supplier: item.supplier || "City Plumbing",
    url: item.url || "",
    manual_price: Number(item.manual_price || item.live_price || item.price || 0),
    required: !item.optional,
    display_status: item.optional ? "optional" : "required",
    data_source: "v15_1_job_bundle",
    material_confidence: Number(item.confidence || 75),
    reason: item.reason || "",
    source: item.source || "",
    price_source: item.price_source || "",
    sku: item.sku || "",
    image_url: item.image_url || "",
    checked_at: item.checked_at || ""
  };
  draft.materials.push(existing);
  return {material: existing, created: true};
}

function mergeBundleMaterialIntoForm(material) {
  const row = findMaterialRowByCanonicalName(material.name || "");
  const incomingQty = Number(material.quantity || 1);

  if (row) {
    const qtyInput = row.querySelector(".m-qty");
    const currentQty = Number(qtyInput?.value || 0);
    if (qtyInput) qtyInput.value = Math.max(currentQty, incomingQty);

    const supplier = row.querySelector(".m-supplier");
    const url = row.querySelector(".m-url");
    const manual = row.querySelector(".m-manual");

    if (supplier && material.supplier) supplier.value = material.supplier;
    if (url && !url.value && material.url) url.value = material.url;
    if (manual && !Number(manual.value || 0) && Number(material.manual_price || 0)) {
      manual.value = Number(material.manual_price || 0);
    }
    updateMaterialLiveBadge(row);
    return false;
  }

  addMaterial({
    name: material.name || "",
    quantity: incomingQty,
    supplier: material.supplier || "City Plumbing",
    url: material.url || "",
    manual_price: Number(material.manual_price || material.live_price || 0),
    source: material.source || "v15_1_job_bundle",
    price_source: material.price_source || "",
    sku: material.sku || "",
    image_url: material.image_url || "",
    checked_at: material.checked_at || "",
    quantity_source: "bundle"
  });
  return true;
}


function mergeDuplicateMaterialRowsInForm() {
  const rows = [...document.querySelectorAll("#materials .material-row")];
  const kept = new Map();

  rows.forEach(row => {
    const name = row.querySelector(".m-name")?.value || "";
    const identity = bundleMaterialIdentity(name);
    if (!identity) return;

    const existingRow = kept.get(identity);
    if (!existingRow) {
      kept.set(identity, row);
      return;
    }

    const currentMaterial = {
      name: existingRow.querySelector(".m-name")?.value || "",
      quantity: Number(existingRow.querySelector(".m-qty")?.value || 0),
      supplier: existingRow.querySelector(".m-supplier")?.value || "",
      url: existingRow.querySelector(".m-url")?.value || "",
      manual_price: Number(existingRow.querySelector(".m-manual")?.value || 0),
    };
    const incomingMaterial = {
      name: row.querySelector(".m-name")?.value || "",
      quantity: Number(row.querySelector(".m-qty")?.value || 0),
      supplier: row.querySelector(".m-supplier")?.value || "",
      url: row.querySelector(".m-url")?.value || "",
      manual_price: Number(row.querySelector(".m-manual")?.value || 0),
    };

    const preferred = mergePreferredMaterialValues(currentMaterial, incomingMaterial);
    existingRow.querySelector(".m-name").value = preferred.name || currentMaterial.name;
    existingRow.querySelector(".m-qty").value = Math.max(
      Number(currentMaterial.quantity || 0),
      Number(incomingMaterial.quantity || 0)
    );
    existingRow.querySelector(".m-supplier").value = preferred.supplier || "City Plumbing";
    existingRow.querySelector(".m-url").value = preferred.url || "";
    existingRow.querySelector(".m-manual").value = Number(preferred.manual_price || 0) || "";
    row.remove();
    updateMaterialLiveBadge(existingRow);
  });
}


let LIVE_QUOTE_REFRESH_TIMER = null;
let LIVE_QUOTE_REFRESH_RUNNING = false;
let LIVE_QUOTE_REFRESH_PENDING = false;

function quotePreviewIsActive() {
  const result = document.getElementById("result");
  return Boolean(
    CURRENT_QUOTE_ID &&
    result &&
    result.innerHTML.trim() &&
    !result.querySelector(".live-refresh-placeholder")
  );
}

function setLiveRefreshStatus(message, state = "working") {
  let box = document.getElementById("liveQuoteRefreshStatus");
  const result = document.getElementById("result");
  if (!result) return;

  if (!box) {
    box = document.createElement("div");
    box.id = "liveQuoteRefreshStatus";
    box.style.cssText = "margin:8px 0;padding:9px 11px;border-radius:10px;font-weight:700;font-size:13px;";
    result.prepend(box);
  }

  const colours = {
    working: ["#eff6ff", "#1d4ed8", "#93c5fd"],
    saved: ["#f0fdf4", "#166534", "#86efac"],
    waiting: ["#fffbeb", "#92400e", "#fcd34d"],
    error: ["#fef2f2", "#991b1b", "#fca5a5"]
  };
  const selected = colours[state] || colours.working;
  box.style.background = selected[0];
  box.style.color = selected[1];
  box.style.border = `1px solid ${selected[2]}`;
  box.textContent = message;
}

function scheduleLiveQuoteRefresh(reason = "Quote details changed") {
  clearTimeout(LIVE_QUOTE_REFRESH_TIMER);

  if (!CURRENT_QUOTE_ID) {
    // A draft has not yet been saved. The editable form still updates immediately.
    return;
  }

  const result = document.getElementById("result");
  if (!result || !result.innerHTML.trim()) return;

  setLiveRefreshStatus(`${reason}. Updating totals…`, "waiting");

  LIVE_QUOTE_REFRESH_TIMER = setTimeout(async () => {
    if (LIVE_QUOTE_REFRESH_RUNNING) {
      LIVE_QUOTE_REFRESH_PENDING = true;
      return;
    }

    LIVE_QUOTE_REFRESH_RUNNING = true;
    setLiveRefreshStatus("Updating quote totals and saved preview…", "working");

    try {
      await generateQuote({
        silent: true,
        autoRefresh: true,
        skipDashboardReload: true
      });
      setLiveRefreshStatus("✓ Quote totals and preview updated automatically.", "saved");
    } catch (error) {
      console.error("Live quote refresh failed", error);
      setLiveRefreshStatus("Automatic refresh failed. Use Update Quote to try again.", "error");
    } finally {
      LIVE_QUOTE_REFRESH_RUNNING = false;
      if (LIVE_QUOTE_REFRESH_PENDING) {
        LIVE_QUOTE_REFRESH_PENDING = false;
        scheduleLiveQuoteRefresh("Further changes detected");
      }
    }
  }, 850);
}

function installLiveQuoteRefreshListeners() {
  const watchedIds = new Set([
    "labour",
    "include_callout_charge",
    "callout_charge",
    "include_travel_charge",
    "travel_charge",
    "include_materials_handling",
    "materials_handling_percent",
    "deposit_percent",
    "job",
    "quote_type",
    "tiling",
    "wall_tiling_m2",
    "floor_tiling_m2",
    "wall_height",
    "customer_supplies_tiles"
  ]);

  document.addEventListener("input", event => {
    const target = event.target;
    if (!target) return;

    if (
      target.closest?.("#materials") &&
      target.matches?.(".m-name, .m-qty, .m-url, .m-manual")
    ) {
      scheduleLiveQuoteRefresh("Material changed");
      return;
    }

    if (watchedIds.has(target.id)) {
      scheduleLiveQuoteRefresh("Quote detail changed");
    }
  });

  document.addEventListener("change", event => {
    const target = event.target;
    if (!target) return;

    if (
      target.closest?.("#materials") &&
      target.matches?.(".m-supplier, .m-qty, .m-manual")
    ) {
      scheduleLiveQuoteRefresh("Material changed");
      return;
    }

    if (watchedIds.has(target.id)) {
      scheduleLiveQuoteRefresh("Quote detail changed");
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", installLiveQuoteRefreshListeners);
} else {
  installLiveQuoteRefreshListeners();
}

function refreshAfterBundleChange() {
  mergeDuplicateMaterialRowsInForm();
  scheduleQuoteLearning();
  scheduleLabourIntelligence();
  updateForgottenItemWarnings();
  updateSupplierPreferenceNotes();
  scheduleLiveQuoteRefresh("Materials changed");
}

function addV151JobBundle(bundleIndex, essentialOnly = false) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) {
    alert("Generate the AI quote draft first.");
    return;
  }

  const bundles = draft.quote_health.job_specific_bundles || [];
  const bundle = bundles[Number(bundleIndex)];
  if (!bundle) {
    alert("This bundle could not be found. Generate the draft again.");
    return;
  }

  let addedToDraft = 0;
  let addedToForm = 0;
  let merged = 0;
  const includedNames = [];

  (bundle.items || []).forEach(item => {
    if (essentialOnly && item.optional) return;

    const result = mergeBundleMaterialIntoDraft(draft, item);
    if (result.created) addedToDraft += 1;
    else merged += 1;

    if (mergeBundleMaterialIntoForm(result.material)) addedToForm += 1;
    result.material.include_in_quote = true;
    if (item.optional) result.material.optional_selected = true;
    item.already_in_quote = true;
    includedNames.push(item.name || "Material");
  });

  // Merge any duplicates already present in the draft.
  const combined = [];
  (draft.materials || []).forEach(material => {
    const identity = bundleMaterialIdentity(material.name || "");
    const existing = combined.find(item =>
      bundleMaterialIdentity(item.name || "") === identity
    );
    if (!existing) {
      combined.push({...material});
      return;
    }

    // Do not double the same bundle requirement. Keep the highest required
    // quantity and the row with the most useful URL/price information.
    existing.quantity = Math.max(
      Number(existing.quantity || 0),
      Number(material.quantity || 0)
    );
    mergePreferredMaterialValues(existing, material);
  });
  draft.materials = combined;

  draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
  if (includedNames.length) {
    draft.quote_health.checks_passed.push(
      `${bundle.display_name || "Bundle"} reviewed: ${includedNames.join(", ")}.`
    );
  }

  LAST_AI_QUOTE_DRAFT = draft;
  (draft.quote_health?.job_specific_bundles || []).forEach(bundle => {
    if (!bundle.health) return;
    const missingEssentials = (bundle.items || []).filter(item => !item.optional && !item.already_in_quote);
    bundle.health.missing_essential_count = missingEssentials.length;
    bundle.health.ready_to_apply = missingEssentials.length === 0;
    if (missingEssentials.length === 0 && bundle.health.score < 90) {
      bundle.health.score = Math.max(90, Number(bundle.health.score || 0));
      bundle.health.status = "healthy";
      bundle.health.label = "Healthy";
    }
  });
  refreshAfterBundleChange();
  renderAIQuoteDraft({draft});

  const mode = essentialOnly ? "essential material" : "bundle material";
  if (!includedNames.length) {
    showNotice("These bundle materials are already present.");
  } else {
    showNotice(
      `${includedNames.length} ${mode}(s) added or merged. The editable Materials section has been updated.`
    );
  }

  // Move the user to the editable material rows on mobile.
  document.getElementById("materials")?.scrollIntoView({behavior: "smooth", block: "start"});
}


let LIVE_PRODUCT_SEARCHES = {};
let LIVE_PRODUCT_RESULTS = {};


function numberFromWordsOrDigits(text, itemPattern) {
  const source = String(text || "").toLowerCase();
  const words = {
    one: 1, two: 2, three: 3, four: 4, five: 5,
    six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
    eleven: 11, twelve: 12
  };
  const pattern = new RegExp(
    `\\b(\\d+(?:\\.\\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\\b[^.\\n]{0,35}${itemPattern}`,
    "i"
  );
  const match = source.match(pattern);
  if (!match) return 0;
  return words[match[1]] || Number(match[1] || 0);
}

function metresFromText(text) {
  const source = String(text || "").toLowerCase();
  const match = source.match(/\b(?:approximately|approx\.?|about|around)?\s*(\d+(?:\.\d+)?)\s*(?:m|metre|metres|meter|meters)\b/i);
  return match ? Number(match[1] || 0) : 0;
}

function upsertDraftMaterial(draft, material) {
  draft.materials = draft.materials || [];
  const incoming = canonicalMaterialName(material.name || "");
  const existing = draft.materials.find(item => {
    const current = canonicalMaterialName(item.name || "");
    return current === incoming ||
      (incoming && current && (current.includes(incoming) || incoming.includes(current)));
  });

  if (existing) {
    existing.quantity = Math.max(Number(existing.quantity || 0), Number(material.quantity || 0));
    existing.required = Boolean(existing.required || material.required);
    existing.display_status = existing.required ? "required" : (material.display_status || existing.display_status);
    existing.status = existing.required ? "required" : (material.status || existing.status);
    existing.reason = material.reason || existing.reason || "";
    existing.material_confidence = Math.max(
      Number(existing.material_confidence || 0),
      Number(material.material_confidence || 0)
    );
    return existing;
  }

  draft.materials.push(material);
  return material;
}

function mergeExplicitSurveyMaterialsIntoDraft(draft) {
  draft.materials = draft.materials || [];

  const jobText = [
    document.getElementById("job")?.value || "",
    draft.scope_of_work || "",
    CURRENT_SITE_SURVEY?.summary || "",
    CURRENT_SITE_SURVEY?.proposed_job_description || "",
    CURRENT_SITE_SURVEY?.site_visit_addition || "",
    CURRENT_SITE_SURVEY?.transcript || ""
  ].join("\n");

  const actions = CURRENT_SITE_SURVEY?.material_actions || [];
  const explicitRequiredText = actions
    .filter(action => action.action === "include_required")
    .map(action => `${action.material_name || ""}. ${action.reason || ""}`)
    .join("\n");

  const combined = `${jobText}\n${explicitRequiredText}`;
  const lower = combined.toLowerCase();

  // Copper pipe: convert stated total metres into purchasable 3m lengths.
  if (/\bcopper\b[^.\n]{0,50}\bpipe(work)?\b|\bpipe(work)?\b[^.\n]{0,50}\bcopper\b/i.test(combined)) {
    const metres = metresFromText(combined);
    if (metres > 0) {
      const lengths = Math.max(1, Math.ceil(metres / 3));
      upsertDraftMaterial(draft, {
        name: "15mm Copper Pipe 3m",
        quantity: lengths,
        supplier: "City Plumbing",
        url: "",
        manual_price: 0,
        required: true,
        display_status: "required",
        status: "required",
        source: "explicit_site_survey",
        data_source: "explicit_site_survey",
        material_confidence: 98,
        reason: `${metres} metres of 15mm copper pipe was explicitly stated; ${lengths} × 3m lengths required before wastage review.`
      });
    }
  }

  // Explicit elbows.
  const elbowQty = numberFromWordsOrDigits(combined, "(?:15\\s*mm\\s*)?(?:end[- ]?feed\\s*)?elbows?");
  if (elbowQty > 0) {
    upsertDraftMaterial(draft, {
      name: "15mm Endfeed Elbow",
      quantity: elbowQty,
      supplier: "City Plumbing",
      url: "",
      manual_price: 0,
      required: true,
      display_status: "required",
      status: "required",
      source: "explicit_site_survey",
      data_source: "explicit_site_survey",
      material_confidence: 99,
      reason: `${elbowQty} elbow fitting(s) were explicitly stated in the job description or site survey.`
    });
  }

  // Explicit tees. If a count is not stated, retain as a site-check item rather than omitting it.
  const teeMentioned = /\b(?:22\s*mm\s*)?(?:end[- ]?feed\s*)?tees?\b/i.test(combined);
  const teeQty = numberFromWordsOrDigits(combined, "(?:22\\s*mm\\s*)?(?:end[- ]?feed\\s*)?tees?");
  if (teeMentioned) {
    upsertDraftMaterial(draft, {
      name: /22\s*mm/i.test(combined) && /15\s*mm\s*(?:branch|reduc)/i.test(combined)
        ? "22mm x 15mm Endfeed Reducing Tee"
        : "Endfeed Tee",
      quantity: teeQty > 0 ? teeQty : 1,
      supplier: "City Plumbing",
      url: "",
      manual_price: 0,
      required: teeQty > 0,
      display_status: teeQty > 0 ? "required" : "site_check",
      status: teeQty > 0 ? "required" : "site_check",
      source: "explicit_site_survey",
      data_source: "explicit_site_survey",
      material_confidence: teeQty > 0 ? 99 : 70,
      reason: teeQty > 0
        ? `${teeQty} tee fitting(s) were explicitly stated.`
        : "Tee fittings were explicitly mentioned, but the quantity was not stated. Confirm before ordering."
    });
  }

  // Explicit radiator valve arrangement.
  const asksTrv = /\btrv\b|thermostatic radiator valve/i.test(combined);
  const asksLockshield = /\blockshield\b/i.test(combined);
  const asksValveSet = /\bradiator valve set\b/i.test(combined) || (asksTrv && asksLockshield);

  if (asksValveSet) {
    upsertDraftMaterial(draft, {
      name: "Radiator Valve Set",
      quantity: 1,
      supplier: "Screwfix",
      url: "",
      manual_price: 0,
      required: true,
      display_status: "required",
      status: "required",
      source: "explicit_site_survey",
      data_source: "explicit_site_survey",
      material_confidence: 99,
      reason: "A TRV and lockshield arrangement was explicitly specified."
    });
  }

  // Inhibitor is required where the description explicitly says refill with inhibitor.
  if (/\binhibitor\b/i.test(combined)) {
    upsertDraftMaterial(draft, {
      name: "Inhibitor 1L",
      quantity: 1,
      supplier: "Toolstation",
      url: "",
      manual_price: 0,
      required: true,
      display_status: "required",
      status: "required",
      source: "explicit_site_survey",
      data_source: "explicit_site_survey",
      material_confidence: 95,
      reason: "Inhibitor was explicitly included in the works."
    });
  }

  return draft;
}

function prepareDraftForV125(draft) {
  draft.materials = draft.materials || [];
  draft = mergeExplicitSurveyMaterialsIntoDraft(draft);
  const scope = String(draft.scope_of_work || document.getElementById("job")?.value || "").toLowerCase();
  const names = draft.materials.map(item => String(item.name || "").toLowerCase());

  // Remove duplicate radiator valve entries. A complete valve set already contains
  // one operating valve/TRV and one lockshield, so separate generic duplicates are removed.
  const hasValveSet = names.some(name => name.includes("radiator valve set"));
  const radiatorMentions = [...scope.matchAll(/\b(?:install|replace|fit|supply)\b[^.\n]{0,80}\bradiator\b/g)].length;
  const likelyRadiatorCount = Math.max(1, radiatorMentions || 1);

  if (hasValveSet) {
    let keptSet = false;
    draft.materials = draft.materials.filter(item => {
      const name = String(item.name || "").toLowerCase().trim();
      if (name.includes("radiator valve set")) {
        if (keptSet) return false;
        keptSet = true;
        item.quantity = Math.min(Number(item.quantity || 1), likelyRadiatorCount);
        return true;
      }
      if (
        name === "trv valve" ||
        name === "thermostatic radiator valve" ||
        name === "lockshield valve" ||
        name === "radiator valve"
      ) return false;
      return true;
    });
  } else {
    // If separate TRV and lockshield are used, allow one of each per radiator only.
    draft.materials.forEach(item => {
      const name = String(item.name || "").toLowerCase().trim();
      if (
        name === "trv valve" ||
        name === "thermostatic radiator valve" ||
        name === "lockshield valve"
      ) {
        item.quantity = Math.min(Number(item.quantity || 1), likelyRadiatorCount);
      }
    });
  }

  // Concealed/new copper routes need fittings, but exact elbows/couplers must not be invented.
  const routeNeedsFittings = /(copper|pipework|flow and return)/.test(scope) && /(metre|meter|route|floorboard|carpet|concealed)/.test(scope);
  const hasFittings = draft.materials.some(item => /elbow|coupler|tee|fittings allowance/i.test(String(item.name || "")));
  if (routeNeedsFittings && !hasFittings) {
    draft.materials.push({
      name: "15mm copper fittings allowance",
      quantity: 1,
      supplier: "City Plumbing",
      url: "",
      manual_price: 0,
      required: false,
      display_status: "site_check",
      status: "site_check",
      source: "v12.5_provisional_allowance",
      material_confidence: 55,
      reason: "Provisional allowance only. Confirm elbow, tee and coupler quantities after the route is exposed or clearly stated."
    });
  }
  draft = enrichDraftMaterialsFromSavedDatabase(draft);
  return draft;
}

function liveProductQueriesFromDraft(draft) {
  const searches = [];
  const existing = (draft.materials || []).map(item => String(item.name || "").toLowerCase());
  const surveyActions = CURRENT_SITE_SURVEY?.material_actions || [];
  const scope = String(draft.scope_of_work || document.getElementById("job")?.value || "").toLowerCase();

  const addSearch = (query, label, reason, productType = "general") => {
    if (!query || searches.some(item => item.query.toLowerCase() === query.toLowerCase())) return;
    searches.push({query, label, reason, productType, requiresChoice: productType === "radiator"});
  };

  surveyActions.forEach(action => {
    if (action.action !== "include_required") return;
    const name = String(action.material_name || "").trim();
    const lower = name.toLowerCase();
    if (/radiator/.test(lower) && !/valve|pipework|connection/.test(lower)) {
      addSearch(name, name, action.reason || "Required by the site survey.", "radiator");
    }
  });

  const radiatorMatch = scope.match(/(\d{3,4})\s*[x×]\s*(\d{3,4})\s*mm?\s*radiator/i);
  if (radiatorMatch && !existing.some(name => name.includes("radiator") && !name.includes("valve"))) {
    addSearch(
      `${radiatorMatch[1]} x ${radiatorMatch[2]}mm white central heating panel radiator`,
      `${radiatorMatch[1]} × ${radiatorMatch[2]} mm radiator`,
      "The quote requires a radiator, but no priced radiator product is in the material list.",
      "radiator"
    );
  }

  // Search for required main valve products that still have no product link.
  (draft.materials || []).forEach(material => {
    const name = String(material.name || "").trim();
    const lower = name.toLowerCase();
    const required = (material.status || material.display_status || (material.required ? "required" : "optional")) === "required";
    if (!required || material.url) return;
    if (lower.includes("radiator valve set")) addSearch("angled thermostatic radiator valve and lockshield set 15mm", name, "Required valve set has no product link.", "radiator_valve_set");
    else if (lower.includes("trv")) addSearch("angled thermostatic radiator valve TRV 15mm", name, "Required TRV has no product link.", "trv");
    else if (lower.includes("lockshield")) addSearch("angled lockshield radiator valve 15mm", name, "Required lockshield has no product link.", "lockshield");
  });

  return searches.slice(0, 6);
}

function liveProductFinderHtml(draft) {
  const searches = liveProductQueriesFromDraft(draft);
  LIVE_PRODUCT_SEARCHES = Object.fromEntries(searches.map((item, index) => [String(index), item]));
  if (!searches.length) return "";

  return `
    <div style="margin-top:10px;padding:10px;border:2px solid #0284c7;border-radius:10px;background:#f0f9ff;">
      <strong>Live merchant product finder</strong><br>
      <span class="small">V13 matches every material against your saved database first, ignoring brand names, word order and common filler words. Saved URLs and cached prices are inherited automatically before a blank material is created. For radiators, you must choose the type before searching. A confirmed product is added directly to the Materials list with its supplier, current price and product URL.</span>
      ${searches.map((item, index) => `
        <div style="margin-top:9px;padding:9px;border:1px solid #bae6fd;border-radius:9px;background:white;">
          <strong>${escapeHtml(item.label)}</strong><br>
          <span class="small">${escapeHtml(item.reason)}</span>
          ${item.productType === "radiator" ? `
            <label class="small" style="display:block;margin-top:9px;font-weight:700;">Choose radiator type before searching</label>
            <select id="radiatorType-${index}" onchange="updateRadiatorSearchButton('${index}')">
              <option value="">— Select radiator type —</option>
              <optgroup label="Standard panel radiators">
                <option value="type 11 panel radiator">Type 11 — single panel, single convector</option>
                <option value="type 21 panel radiator">Type 21 — double panel, single convector</option>
                <option value="type 22 panel radiator">Type 22 — double panel, double convector</option>
              </optgroup>
              <optgroup label="Other radiator styles">
                <option value="towel radiator">Towel radiator</option>
                <option value="vertical radiator">Vertical radiator</option>
                <option value="designer radiator">Designer radiator</option>
                <option value="column radiator">Column radiator</option>
              </optgroup>
              <optgroup label="Existing or customer choice">
                <option value="like for like radiator">Like for like / match existing</option>
                <option value="customer selected radiator">Customer-selected product</option>
              </optgroup>
            </select>
            <div id="radiatorChoiceNote-${index}" class="small" style="margin-top:5px;color:#92400e;">
              The app will not choose Type 11, 21 or 22 automatically.
            </div>` : ""}
          <div class="history-actions" style="grid-template-columns:1fr;margin-top:7px;">
            <button type="button" id="liveSearchButton-${index}" class="btn-green" ${item.productType === "radiator" ? "disabled" : ""} onclick="searchLiveMerchantProduct('${index}')">Find matching products</button>
          </div>
          <div id="liveProductResults-${index}" style="margin-top:7px;"></div>
        </div>
      `).join("")}
      <div class="small" style="margin-top:8px;">Prices and availability can change. Open the merchant page and confirm before ordering.</div>
    </div>`;
}


function updateRadiatorSearchButton(searchId) {
  const select = document.getElementById(`radiatorType-${searchId}`);
  const button = document.getElementById(`liveSearchButton-${searchId}`);
  const note = document.getElementById(`radiatorChoiceNote-${searchId}`);
  if (!select || !button) return;

  const value = String(select.value || "").trim();
  button.disabled = !value;

  if (!note) return;
  if (!value) {
    note.textContent = "The app will not choose Type 11, 21 or 22 automatically.";
  } else if (value === "like for like radiator") {
    note.textContent = "The search will look for a matching radiator, but the existing type and depth still need confirming.";
  } else if (value === "customer selected radiator") {
    note.textContent = "No merchant product will be assumed. Choose the customer’s exact product or paste its URL.";
  } else {
    note.textContent = `Search locked to: ${select.options[select.selectedIndex].text}.`;
  }
}

async function searchLiveMerchantProduct(searchId) {
  const search = LIVE_PRODUCT_SEARCHES[String(searchId)];
  const box = document.getElementById(`liveProductResults-${searchId}`);
  if (!search || !box) return;
  box.innerHTML = "Searching City Plumbing, Screwfix, Toolstation and Selco…";

  try {
    const typeSelect = document.getElementById(`radiatorType-${searchId}`);
    const selectedType = String(typeSelect?.value || "").trim();

    if (search.productType === "radiator" && !selectedType) {
      box.innerHTML = `<div class="notice" style="border-color:#d97706;">Choose the radiator type first. No type has been assumed.</div>`;
      return;
    }

    if (selectedType === "customer selected radiator") {
      box.innerHTML = `
        <div class="notice">
          Customer-selected radiator: open the customer’s product, then add its exact product URL, supplier and price to the Materials list.
          The app will not substitute a different radiator automatically.
        </div>`;
      return;
    }

    const refinedQuery = [search.query, selectedType].filter(Boolean).join(" ");
    const response = await fetch("/api/live-product-search?q=" + encodeURIComponent(refinedQuery));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Merchant search failed.");
    const results = data.results || [];
    LIVE_PRODUCT_RESULTS[String(searchId)] = results;

    if (!results.length) {
      box.innerHTML = `<div class="notice">No merchant matches were found. Try a more specific product description.</div>`;
      return;
    }

    box.innerHTML = results.map((item, resultIndex) => `
      <div style="margin-top:7px;padding:9px;border:1px solid #ddd;border-radius:9px;background:#fff;">
        <strong>${escapeHtml(item.name || "")}</strong><br>
        <span class="small">
          ${escapeHtml(item.supplier || "")}
          ${item.live_price ? ` · <strong>${pounds(item.live_price)}</strong>` : " · price unavailable"}
          ${item.availability ? ` · ${escapeHtml(item.availability)}` : ""}
          ${item.sku ? ` · SKU ${escapeHtml(item.sku)}` : ""}
          ${item.search_only ? "" : ` · ${Number(item.match_score || 0)}% strict match`}
        </span>
        ${item.image_url ? `<img src="${escapeHtml(item.image_url)}" alt="" loading="lazy" style="display:block;max-width:110px;max-height:90px;object-fit:contain;margin-top:7px;border-radius:6px;">` : ""}
        <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:7px;margin-top:7px;">
          <button type="button" class="btn-light" onclick='window.open(${JSON.stringify(item.url || "")}, "_blank", "noopener")'>
            ${item.search_only ? "Open merchant search" : "View product"}
          </button>
          ${item.search_only ? "" : `<button type="button" class="btn-green" onclick="addLiveMerchantProduct('${searchId}', ${resultIndex})">Add to quote</button>`}
        </div>
      </div>
    `).join("");
  } catch (error) {
    box.innerHTML = `<div class="notice" style="border-color:#dc2626;">${escapeHtml(error.message || "Merchant search failed.")}</div>`;
  }
}

function findExistingMaterialRowByUrlOrName(url, name) {
  const cleanUrl = String(url || "").split("?")[0].replace(/\/+$/, "").toLowerCase();
  const canonical = canonicalMaterialName(name || "");
  return [...document.querySelectorAll("#materials .material-row")].find(row => {
    const rowUrl = String(row.querySelector(".m-url")?.value || "").split("?")[0].replace(/\/+$/, "").toLowerCase();
    const rowName = canonicalMaterialName(row.querySelector(".m-name")?.value || "");
    return (cleanUrl && rowUrl === cleanUrl) || (canonical && rowName === canonical);
  });
}

function addLiveMerchantProduct(searchId, resultIndex) {
  const item = LIVE_PRODUCT_RESULTS[String(searchId)]?.[Number(resultIndex)];
  if (!item || !LAST_AI_QUOTE_DRAFT) return;

  const productUrl = String(item.url || "").trim();
  if (!/^https?:\/\//i.test(productUrl) || item.search_only) {
    showNotice("Open the merchant result and choose a confirmed product page before adding it.");
    return;
  }

  const product = {
    name: item.name || "",
    quantity: 1,
    supplier: item.supplier || "City Plumbing",
    url: productUrl,
    manual_price: Number(item.live_price || item.default_price || 0),
    live_price: Number(item.live_price || item.default_price || 0),
    status: "required",
    source: "live_merchant_search",
    price_source: item.price_source || "live",
    image_url: item.image_url || "",
    sku: item.sku || "",
    checked_at: item.checked_at || new Date().toISOString()
  };

  LAST_AI_QUOTE_DRAFT.materials = LAST_AI_QUOTE_DRAFT.materials || [];
  const canonical = canonicalMaterialName(product.name);
  const existingDraftIndex = LAST_AI_QUOTE_DRAFT.materials.findIndex(existing => {
    const existingUrl = String(existing.url || "").split("?")[0].replace(/\/+$/, "").toLowerCase();
    const incomingUrl = product.url.split("?")[0].replace(/\/+$/, "").toLowerCase();
    return (existingUrl && existingUrl === incomingUrl) ||
           canonicalMaterialName(existing.name || "") === canonical;
  });

  if (existingDraftIndex >= 0) {
    LAST_AI_QUOTE_DRAFT.materials[existingDraftIndex] = {
      ...LAST_AI_QUOTE_DRAFT.materials[existingDraftIndex],
      ...product
    };
  } else {
    LAST_AI_QUOTE_DRAFT.materials.unshift(product);
  }

  // Re-merge explicitly stated ancillary materials after selecting the main
  // merchant product. This prevents the radiator choice from becoming the
  // only material in the applied quote.
  LAST_AI_QUOTE_DRAFT = prepareDraftForV125(LAST_AI_QUOTE_DRAFT);

  const existingRow = findExistingMaterialRowByUrlOrName(product.url, product.name);
  if (existingRow) {
    existingRow.querySelector(".m-name").value = product.name;
    existingRow.querySelector(".m-qty").value = product.quantity;
    existingRow.querySelector(".m-supplier").value = product.supplier;
    existingRow.querySelector(".m-url").value = product.url;
    existingRow.querySelector(".m-manual").value = product.manual_price || "";
    existingRow.dataset.liveProduct = "1";
    existingRow.dataset.sku = product.sku || "";
    existingRow.dataset.imageUrl = product.image_url || "";
    existingRow.dataset.checkedAt = product.checked_at || "";
    updateMaterialLiveBadge(existingRow);
  } else {
    addMaterial(product);
  }

  renderAIQuoteDraft({draft: LAST_AI_QUOTE_DRAFT});
  showNotice(`${product.name} added to the materials list with supplier, price and product URL.`);
}



function isOptionalDraftMaterial(material) {
  const status = String(
    material?.display_status ||
    material?.status ||
    (material?.required ? "required" : "optional")
  ).toLowerCase();
  return !material?.required && status !== "required" && status !== "customer_supplied";
}

function optionalMaterialIsSelected(material) {
  if (!isOptionalDraftMaterial(material)) return true;
  return material?.include_in_quote === true || material?.optional_selected === true;
}

function removeMaterialRowByIdentity(materialName) {
  const identity = bundleMaterialIdentity(materialName || "");
  const row = [...document.querySelectorAll("#materials .material-row")].find(candidate =>
    bundleMaterialIdentity(candidate.querySelector(".m-name")?.value || "") === identity
  );
  if (row) row.remove();
}

function toggleOptionalDraftMaterial(materialIndex, forceValue = null) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !Array.isArray(draft.materials)) return;

  const material = draft.materials[Number(materialIndex)];
  if (!material || !isOptionalDraftMaterial(material)) return;

  const selected = forceValue === null
    ? !optionalMaterialIsSelected(material)
    : Boolean(forceValue);

  material.include_in_quote = selected;
  material.optional_selected = selected;

  if (selected) {
    const enriched = enrichMaterialFromSavedDatabase({...material});
    Object.assign(material, enriched);
    mergeBundleMaterialIntoForm(material);
    mergeDuplicateMaterialRowsInForm();
    showNotice(`${material.name} added to the editable Materials list.`);
  } else {
    removeMaterialRowByIdentity(material.name || "");
    showNotice(`${material.name} removed from the editable Materials list.`);
  }

  LAST_AI_QUOTE_DRAFT = draft;
  refreshAfterBundleChange();
  renderAIQuoteDraft({draft});
}

function optionalMaterialControl(material, index) {
  if (!isOptionalDraftMaterial(material)) {
    return `<span style="display:inline-block;padding:4px 8px;border-radius:999px;background:#dcfce7;color:#166534;font-size:12px;font-weight:700;">Included</span>`;
  }

  const selected = optionalMaterialIsSelected(material);
  return `
    <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;white-space:nowrap;">
      <input type="checkbox" ${selected ? "checked" : ""}
        onchange="toggleOptionalDraftMaterial(${index}, this.checked)"
        style="width:18px;height:18px;margin:0;">
      <span style="font-size:12px;font-weight:700;color:${selected ? "#166534" : "#374151"};">
        ${selected ? "Added" : "Add"}
      </span>
    </label>`;
}

function initialiseOptionalMaterialSelections(draft) {
  (draft?.materials || []).forEach(material => {
    if (!isOptionalDraftMaterial(material)) {
      material.include_in_quote = true;
      return;
    }
    if (typeof material.include_in_quote !== "boolean") {
      material.include_in_quote = false;
      material.optional_selected = false;
    }
  });
  return draft;
}


function bundleHealthColour(status) {
  if (status === "healthy") return {border:"#16a34a", background:"#f0fdf4", text:"#166534"};
  if (status === "incomplete") return {border:"#dc2626", background:"#fef2f2", text:"#991b1b"};
  return {border:"#d97706", background:"#fffbeb", text:"#92400e"};
}

function bundleHealthIssueIcon(severity) {
  if (severity === "high") return "✕";
  if (severity === "medium") return "△";
  if (severity === "low") return "•";
  return "ℹ";
}

function renderBundleHealth(bundle) {
  const health = bundle.health || {};
  const colours = bundleHealthColour(health.status || "review");
  const issues = health.issues || [];
  const checks = health.checks || [];

  return `
    <div style="margin-top:8px;padding:9px;border:1px solid ${colours.border};border-radius:9px;background:${colours.background};color:${colours.text};">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
        <div>
          <strong>Bundle health</strong><br>
          <span class="small">${escapeHtml(health.label || "Review recommended")}</span>
        </div>
        <strong style="font-size:22px;">${Number(health.score || 0)}%</strong>
      </div>
      ${issues.length ? `<div style="margin-top:7px;">${issues.map(issue => `
        <div style="margin-top:4px;">
          ${bundleHealthIssueIcon(issue.severity)} ${escapeHtml(issue.message || "")}
          ${(issue.items || []).length ? `<br><span class="small" style="display:inline-block;margin-left:14px;">${(issue.items || []).map(escapeHtml).join(", ")}</span>` : ""}
        </div>`).join("")}</div>` : ""}
      ${checks.length ? `<details style="margin-top:7px;"><summary style="cursor:pointer;font-weight:700;">Passed checks</summary><div class="small" style="margin-top:5px;">${checks.map(check => `✓ ${escapeHtml(check)}`).join("<br>")}</div></details>` : ""}
    </div>`;
}

function renderAIQuoteDraft(data) {
  const box = document.getElementById("aiQuoteResult");
  if (!box) return;

  const draft = initialiseOptionalMaterialSelections(
    prepareDraftForV125(data.draft || {})
  );
  LAST_AI_QUOTE_DRAFT = draft;
  const materials = draft.materials || [];
  const professional = draft.professional_quote || {};
  const confidence = professional.confidence || {};
  const quality = draft.quote_quality || {};
  const assumptions = professional.assumptions || [];
  const exclusions = professional.exclusions || [];
  const questions = professional.questions || [];
  const risks = professional.risk_notes || [];
  const technical = draft.technical_detail || {};
  const evidence = professional.material_evidence || [];
  const preview = draft.customer_preview || {};
  const health = draft.quote_health || {};
  const healthMissing = health.missing_items || [];
  const healthQuantities = health.quantity_warnings || [];
  const healthLabour = health.labour_warnings || [];
  const healthPassed = health.checks_passed || [];
  const jobBundles = health.job_specific_bundles || [];
  const surveySummary = draft.site_survey_summary || {};

  const statusBadge = (status) => {
    if (status === "required") return `<span style="display:inline-block;padding:2px 7px;border-radius:999px;background:#dcfce7;font-size:12px;">Required</span>`;
    if (status === "customer_supplied") return `<span style="display:inline-block;padding:2px 7px;border-radius:999px;background:#dbeafe;font-size:12px;">Customer supplied</span>`;
    if (status === "site_check") return `<span style="display:inline-block;padding:2px 7px;border-radius:999px;background:#fef3c7;font-size:12px;">Site check</span>`;
    return `<span style="display:inline-block;padding:2px 7px;border-radius:999px;background:#f3f4f6;font-size:12px;">Optional</span>`;
  };

  const stars = "★".repeat(Number(quality.stars || 0)) + "☆".repeat(Math.max(0, 5 - Number(quality.stars || 0)));

  box.innerHTML = `
    <div class="history-item" style="padding:10px;border-color:#7c3aed;">
      <div style="display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:12px;background:#f3f4f6;border-radius:10px;">
        <div>
          <strong style="font-size:18px;">Estimator dashboard, learning & fixes</strong><br>
          <span style="font-size:22px;letter-spacing:2px;">${stars}</span><br>
          <span class="small">Overall estimate quality ${Number(quality.overall || 0)}%</span>
        </div>
        <div style="text-align:center;min-width:90px;">
          <div style="font-size:30px;font-weight:800;">${Number(confidence.score || 0)}%</div>
          <div class="small">${escapeHtml(confidence.level || "unknown")} confidence</div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:8px;">
        <div style="padding:8px;border:1px solid #ddd;border-radius:8px;"><strong>${Number(quality.materials || 0)}%</strong><br><span class="small">Materials</span></div>
        <div style="padding:8px;border:1px solid #ddd;border-radius:8px;"><strong>${Number(quality.labour || 0)}%</strong><br><span class="small">Labour</span></div>
        <div style="padding:8px;border:1px solid #ddd;border-radius:8px;"><strong>${Number(quality.understanding || 0)}%</strong><br><span class="small">AI understanding</span></div>
        <div style="padding:8px;border:1px solid #ddd;border-radius:8px;"><strong>${Number(quality.site_confirmation || 0)}%</strong><br><span class="small">Needs site confirmation</span></div>
      </div>

      <div style="margin-top:9px;padding:10px;border:2px solid ${health.readiness === "ready_to_send" ? "#16a34a" : health.readiness === "do_not_send" ? "#dc2626" : "#d97706"};border-radius:9px;background:${health.readiness === "ready_to_send" ? "#f0fdf4" : health.readiness === "do_not_send" ? "#fef2f2" : "#fffbeb"};">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
          <div><strong>Quote health</strong><br><span class="small">${escapeHtml(health.readiness_label || "Review recommended")}</span></div>
          <div style="font-size:25px;font-weight:800;">${Number(health.score || 0)}%</div>
        </div>

        ${healthPassed.length ? `<div style="margin-top:7px;">${healthPassed.map(x => `✓ ${escapeHtml(x)}`).join("<br>")}</div>` : ""}

        ${healthMissing.length ? `<div style="margin-top:9px;"><strong>Possible missing items</strong>
          ${healthMissing.map(item => `<div style="margin-top:6px;padding:8px;background:white;border:1px solid #ddd;border-radius:8px;">
            <strong>${escapeHtml(item.name || "")}</strong> × ${Number(item.quantity || 1)} ${item.optional ? `<span class="small">(optional)</span>` : ""}<br>
            <span class="small">${escapeHtml(item.reason || "")}</span>
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:6px;margin-top:7px;">
              <button type="button" class="btn-light" onclick='addQuoteHealthSuggestion(${JSON.stringify(item.id)})'>Add item</button>
              <button type="button" class="btn-light" onclick='ignoreQuoteHealthSuggestion(${JSON.stringify(item.id)})'>Ignore</button>
            </div>
          </div>`).join("")}
        </div>` : ""}

        ${healthQuantities.length ? `<div style="margin-top:9px;"><strong>Quantities to check</strong>
          ${healthQuantities.map(x => `<div style="margin-top:6px;padding:8px;background:white;border:1px solid #ddd;border-radius:8px;">
            <strong>${escapeHtml(x.material || "")}</strong><br>
            <span class="small">${escapeHtml(x.message || "")}</span>
            ${x.no_auto_fix ? "" : `<div style="margin-top:6px;"><strong>Current:</strong> ${Number(x.actual_quantity || 0)} &nbsp; <strong>Suggested:</strong> ${Number(x.suggested_quantity || 0)}</div>
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:6px;margin-top:7px;">
              <button type="button" class="btn-light" onclick='useSuggestedQuantity(${JSON.stringify(x.id)})'>Use suggested</button>
              <button type="button" class="btn-light" onclick='keepCurrentQuantity(${JSON.stringify(x.id)})'>Keep current</button>
            </div>`}
          </div>`).join("")}
        </div>` : ""}
        ${healthLabour.length ? `<div style="margin-top:9px;"><strong>Labour checks</strong><br>${healthLabour.map(x => `△ ${escapeHtml(x.message || "")}`).join("<br>")}</div>` : ""}
        <div class="small" style="margin-top:7px;">Advisory only — nothing is added or repriced unless you approve it.</div>
      </div>

      ${jobBundles.length ? `<div style="margin-top:10px;"><strong>Recommended job bundles</strong>
        ${jobBundles.map((bundle, bundleIndex) => {
          const pendingAll = (bundle.items || []).filter(item => !item.already_in_quote).length;
          const pendingEssential = (bundle.items || []).filter(item => !item.already_in_quote && !item.optional).length;
          const health = bundle.health || {};
          const colours = bundleHealthColour(health.status || "review");
          return `<div style="margin-top:7px;padding:9px;border:1px solid ${colours.border};border-radius:9px;background:white;">
            <strong>${escapeHtml(bundle.display_name || "")}</strong>
            <span class="small"> · ${Number(bundle.required_count || 0)} essential · ${Number(bundle.optional_count || 0)} optional</span><br>
            ${(bundle.items || []).map(item => `• <strong>${escapeHtml(item.name)}</strong> × ${Number(item.quantity || 1)} — ${Number(item.confidence || 0)}% ${item.already_in_quote ? "✓ already included" : item.optional ? "(optional)" : "(essential)"}${item.reason ? `<br><span class="small" style="display:inline-block;margin-left:12px;">${escapeHtml(item.reason)}</span>` : ""}`).join("<br>")}
            ${renderBundleHealth(bundle)}
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:6px;margin-top:7px;">
              <button type="button" class="btn-green" ${pendingAll ? "" : "disabled"} onclick="addV151JobBundle(${bundleIndex}, false)">
                ${pendingAll ? `Add full bundle (${pendingAll})` : "Full bundle added"}
              </button>
              <button type="button" class="btn-light" ${pendingEssential ? "" : "disabled"} onclick="addV151JobBundle(${bundleIndex}, true)">
                ${pendingEssential ? `Fix missing essentials (${pendingEssential})` : "Essentials complete"}
              </button>
            </div>
          </div>`;
        }).join("")}
      </div>` : ""}

      ${(confidence.positive_reasons || []).length || (confidence.gaps || []).length ? `
        <div style="margin-top:8px;padding:9px;border:1px solid #ddd;border-radius:8px;">
          <strong>Why this estimate is reliable</strong><br>
          ${(confidence.positive_reasons || []).map(x => `✓ ${escapeHtml(x)}`).join("<br>")}
          ${(confidence.gaps || []).map(x => `<br>△ ${escapeHtml(x)}`).join("")}
        </div>` : ""}

      ${surveySummary.used ? `<div style="margin-top:10px;padding:9px;border:1px solid #2563eb;border-radius:8px;background:#eff6ff;"><strong>Site survey used</strong><br>${escapeHtml(surveySummary.summary || "")}${(surveySummary.material_actions_applied || []).length ? `<div style="margin-top:6px;">${(surveySummary.material_actions_applied || []).map(item => `• ${escapeHtml(item.material_name)} — ${escapeHtml(surveyActionLabel(item.action))} (${Number(item.confidence || 0)}%)`).join("<br>")}</div>` : ""}</div>` : ""}

      <div style="margin-top:12px;"><strong>Scope of works</strong></div>
      ${(draft.job_breakdown || []).length ? `
        ${(draft.job_breakdown || []).map(job => `
          <div style="margin-top:7px;padding:9px;border:1px solid #ddd;border-radius:8px;">
            <strong>${escapeHtml(job.display_name || job.job_type || "")}</strong><br>
            ${escapeHtml(job.scope || job.original_text || "")}
          </div>`).join("")}
      ` : `<div style="margin-top:5px;">${escapeHtml(draft.scope_of_work || "")}</div>`}

      <div style="margin-top:12px;"><strong>Labour breakdown</strong>
        <div style="overflow-x:auto;margin-top:5px;">
          <table style="width:100%;border-collapse:collapse;">
            <thead><tr>
              <th style="text-align:left;padding:5px;border-bottom:1px solid #ddd;">Job</th>
              <th style="text-align:right;padding:5px;border-bottom:1px solid #ddd;">Labour</th>
            </tr></thead>
            <tbody>
              ${(draft.job_breakdown || []).length ? (draft.job_breakdown || []).map(job => `<tr>
                <td style="padding:5px;border-bottom:1px solid #eee;">${escapeHtml(job.display_name || job.job_type || "")}</td>
                <td style="padding:5px;text-align:right;border-bottom:1px solid #eee;">${pounds(job.labour_suggestion || 0)}</td>
              </tr>`).join("") : `<tr><td style="padding:5px;border-bottom:1px solid #eee;">Estimated labour</td><td style="padding:5px;text-align:right;border-bottom:1px solid #eee;">${pounds(draft.labour_suggestion || 0)}</td></tr>`}
              <tr><td style="padding:6px;font-weight:800;">Total</td><td style="padding:6px;text-align:right;font-weight:800;">${pounds(draft.labour_suggestion || 0)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div style="margin-top:12px;"><strong>Materials</strong><br>
        <span class="small">Required items are included automatically. Tick an optional item to add it directly to the editable Materials list.</span>
        <div style="overflow-x:auto;margin-top:5px;">
          <table style="width:100%;border-collapse:collapse;min-width:720px;">
            <thead><tr>
              <th style="text-align:left;padding:5px;border-bottom:1px solid #ddd;">Item</th>
              <th style="text-align:left;padding:5px;border-bottom:1px solid #ddd;">Status</th>
              <th style="text-align:center;padding:5px;border-bottom:1px solid #ddd;">Include</th>
              <th style="text-align:right;padding:5px;border-bottom:1px solid #ddd;">Qty</th>
              <th style="text-align:right;padding:5px;border-bottom:1px solid #ddd;">Price</th>
              <th style="text-align:center;padding:5px;border-bottom:1px solid #ddd;">Confidence</th>
              <th style="text-align:left;padding:5px;border-bottom:1px solid #ddd;">Supplier</th>
            </tr></thead>
            <tbody>${materials.length ? materials.map((m, materialIndex) => `<tr style="background:${isOptionalDraftMaterial(m) && !optionalMaterialIsSelected(m) ? "#fafafa" : "white"};">
              <td style="padding:5px;border-bottom:1px solid #eee;"><strong>${escapeHtml(m.name || "")}</strong>${m.reason ? `<br><span class="small">${escapeHtml(m.reason)}</span>` : ""}</td>
              <td style="padding:5px;border-bottom:1px solid #eee;">${statusBadge(m.display_status || (m.required ? "required" : "optional"))}</td>
              <td style="padding:5px;text-align:center;border-bottom:1px solid #eee;">${optionalMaterialControl(m, materialIndex)}</td>
              <td style="padding:5px;text-align:right;border-bottom:1px solid #eee;">${Number(m.quantity || 1)}</td>
              <td style="padding:5px;text-align:right;border-bottom:1px solid #eee;">${Number(m.manual_price || 0) > 0 ? pounds(m.manual_price) : "TBC"}</td>
              <td style="padding:5px;text-align:center;border-bottom:1px solid #eee;">${Number(m.material_confidence || 65)}%</td>
              <td style="padding:5px;border-bottom:1px solid #eee;">${escapeHtml(m.supplier || "")}</td>
            </tr>`).join("") : `<tr><td colspan="7" style="padding:7px;">No materials suggested.</td></tr>`}</tbody>
          </table>
        </div>
      </div>

      ${assumptions.length ? `<div style="margin-top:12px;"><strong>Assumptions</strong>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:7px;margin-top:6px;">
          ${assumptions.map(x => `<div style="padding:8px;border:1px solid #ddd;border-radius:8px;">✓ ${escapeHtml(x)}</div>`).join("")}
        </div>
      </div>` : ""}

      ${exclusions.length ? `<div style="margin-top:12px;"><strong>Exclusions</strong><br>${exclusions.map(x => `• ${escapeHtml(x)}`).join("<br>")}</div>` : ""}
      ${questions.length ? `<div style="margin-top:12px;"><strong>Site checks required</strong><br>${questions.map(x => `• ${escapeHtml(x)}`).join("<br>")}</div>` : ""}
      ${risks.length ? `<div style="margin-top:12px;"><strong>Possible additional work</strong><br>${risks.map(x => `• ${escapeHtml(x)}`).join("<br>")}</div>` : ""}

      ${draft.multi_job_summary ? `<div style="margin-top:12px;padding:9px;background:#eef6ff;border-radius:8px;"><strong>Quote summary</strong><br>
        ${Number(draft.multi_job_summary.job_count || 0)} job(s) ·
        ${Number(draft.multi_job_summary.combined_material_count || 0)} unique material item(s) ·
        ${Number(draft.multi_job_summary.duplicates_merged || 0)} duplicate item(s) merged ·
        labour ${pounds(draft.multi_job_summary.combined_labour || 0)} ·
        materials ${pounds(draft.multi_job_summary.materials_total_before_handling || 0)} before handling
      </div>` : ""}

      ${liveProductFinderHtml(draft)}

      <details style="margin-top:10px;">
        <summary><strong>Internal estimator detail</strong></summary>
        <div style="margin-top:8px;padding:8px;background:#fafafa;border-radius:8px;">
          ${evidence.length ? `<strong>Material evidence</strong><br>${evidence.map(x => `• ${escapeHtml(x.name)} — ${escapeHtml(x.source)} · ${Number(x.confidence || 0)}%${Number(x.used_count || 0) ? ` · ${Number(x.used_count)} prior use(s)` : ""}`).join("<br>")}<br><br>` : ""}
          ${(technical.all_risk_notes || []).length ? `<strong>All risk notes</strong><br>${(technical.all_risk_notes || []).map(x => `• ${escapeHtml(x)}`).join("<br>")}<br><br>` : ""}
          ${(technical.all_questions || []).length ? `<strong>All questions</strong><br>${(technical.all_questions || []).map(x => `• ${escapeHtml(x)}`).join("<br>")}<br><br>` : ""}
          ${(technical.all_warnings || []).length ? `<strong>All warnings</strong><br>${(technical.all_warnings || []).map(x => `• ${escapeHtml(x)}`).join("<br>")}` : ""}
        </div>
      </details>

      <details style="margin-top:10px;">
        <summary><strong>Customer preview</strong></summary>
        <div style="margin-top:8px;padding:12px;background:white;border:1px solid #ddd;border-radius:8px;">
          <h3 style="margin:0 0 8px 0;">Nigel Harvey Ltd</h3>
          <strong>Works included</strong><br>
          ${escapeHtml(preview.scope_of_work || draft.scope_of_work || "")}
          <div style="margin-top:10px;"><strong>Labour</strong><br>${pounds(preview.labour_total || draft.labour_suggestion || 0)}</div>
          ${(preview.exclusions || exclusions).length ? `<div style="margin-top:10px;"><strong>Exclusions</strong><br>${(preview.exclusions || exclusions).map(x => `• ${escapeHtml(x)}`).join("<br>")}</div>` : ""}
        </div>
      </details>

      <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;">
        <button type="button" class="btn-green" onclick="applyAIQuoteDraft()">Apply draft to form</button>
        <button type="button" class="btn-light" onclick="discardAIQuoteDraft()">Discard</button>
      </div>
    </div>`;
}

function applyAIQuoteDraft() {
  let draft = LAST_AI_QUOTE_DRAFT;
  if (!draft) return;
  draft = prepareDraftForV125(draft);
  LAST_AI_QUOTE_DRAFT = draft;

  if (draft.scope_of_work) {
    document.getElementById("job").value = draft.scope_of_work;
  }

  if (Number(draft.labour_suggestion || 0) > 0) {
    document.getElementById("labour").value = Number(draft.labour_suggestion).toFixed(2);
  }

  clearMaterials();
  (draft.materials || [])
    .filter(m => !isOptionalDraftMaterial(m) || optionalMaterialIsSelected(m))
    .forEach(m => {
      addMaterial({
        name: m.name || "",
        quantity: Number(m.quantity || 1),
        supplier: m.supplier || "City Plumbing",
        url: m.url || "",
        manual_price: Number(m.manual_price || m.live_price || m.default_price || 0),
        source: m.source || "",
        price_source: m.price_source || "",
        sku: m.sku || "",
        image_url: m.image_url || "",
        checked_at: m.checked_at || "",
        quantity_source: m.quantity_source || "ai",
        learned_used_count: Number(m.learned_used_count || 0)
      });
    });
  mergeDuplicateMaterialRowsInForm();
  AI_QUOTE_DRAFT_PENDING = false;

  scheduleQuoteLearning();
  scheduleLabourIntelligence();
  updateForgottenItemWarnings();
  updateSupplierPreferenceNotes();

  const box = document.getElementById("aiQuoteResult");
  if (box) {
    box.innerHTML = `<div class="notice">AI draft applied. Check quantities, product links, prices, labour and scope before saving.</div>`;
  }
  showNotice("AI quote draft applied for review.");
}

function discardAIQuoteDraft() {
  clearAIQuoteDraftState();
  showNotice("AI draft discarded.");
}


async function generateQuote(options = {}) {
  const {
    silent = false,
    autoRefresh = false,
    skipDashboardReload = false
  } = options || {};

  // A second click must not start another POST before the first save returns an ID.
  if (!CURRENT_QUOTE_ID && QUOTE_CREATE_IN_PROGRESS) return null;

  const errorBox = document.getElementById("error");
  errorBox.style.display = "none";

  if (AI_QUOTE_DRAFT_PENDING && LAST_AI_QUOTE_DRAFT) {
    if (silent) {
      throw new Error("A pending AI quote draft must be reviewed before saving.");
    }
    const applyDraft = confirm(
      "An AI quote draft is ready but has not been applied. Apply its scope, labour and selected materials before generating the quote?"
    );
    if (!applyDraft) {
      errorBox.innerText = "Quote not generated. Apply or discard the pending AI draft first.";
      errorBox.style.display = "block";
      return null;
    }
    applyAIQuoteDraft();
  }

  const payload = collectFormPayload();
  const isEditing = !!CURRENT_QUOTE_ID;
  const url = isEditing ? "/api/quotes/" + CURRENT_QUOTE_ID : "/api/quote";
  const method = isEditing ? "PUT" : "POST";
  const createButton = !isEditing
    ? document.querySelector('#quotesTab button[onclick="generateQuote()"]')
    : null;
  if (!isEditing) {
    QUOTE_CREATE_IN_PROGRESS = true;
    if (createButton) {
      createButton.disabled = true;
      createButton.innerText = "Generating Quote…";
    }
  }

  try {
    const res = await fetch(url, {
      method,
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error();
    const data = await res.json();

    CURRENT_QUOTE_ID = data.id || null;
    setEditingStatus(CURRENT_QUOTE_ID ? "Editing saved quote #" + CURRENT_QUOTE_ID : "", !!CURRENT_QUOTE_ID);
    setQuoteButtonMode(!!CURRENT_QUOTE_ID);

    renderQuoteResult(data.result);

    // Clear any stale error message after a successful save/update.
    if (errorBox) {
      errorBox.innerText = "";
      errorBox.style.display = "none";
    }

    if (!skipDashboardReload) {
      await loadHistory();
      await loadCustomers();
      await loadDashboard();
    }
    if (!silent) {
      showNotice(isEditing ? "Quote updated." : "Quote saved.");
    }
    return data;
  } catch (err) {
    if (!silent) {
      errorBox.innerText = isEditing ? "Something went wrong updating the quote." : "Something went wrong generating the quote.";
      errorBox.style.display = "block";
    }
    if (autoRefresh || silent) throw err;
    return null;
  } finally {
    if (!isEditing) {
      QUOTE_CREATE_IN_PROGRESS = false;
      if (createButton) createButton.disabled = false;
      setQuoteButtonMode(!!CURRENT_QUOTE_ID);
    }
  }
}

async function convertQuoteToInvoice(quoteId) {
  try {
    const res = await fetch("/api/quotes/" + quoteId + "/to-invoice", { method: "POST" });
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    showTab("invoicesTab");
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice created from quote.");
  } catch (e) {
    alert("Could not convert quote to invoice.");
  }
}

async function convertCurrentQuoteToInvoice() {
  if (!CURRENT_QUOTE_ID) {
    alert("Generate and save the quote first.");
    return;
  }
  await convertQuoteToInvoice(CURRENT_QUOTE_ID);
}


function normaliseQuoteDataForEditing(data) {
  const q = data && (data.request || data.quote || data.result || data);
  return {
    quote_type: q.quote_type || q.type || "small",
    customer_name: q.customer_name || q.customer || "",
    customer_address: q.customer_address || q.address || "",
    customer_phone: q.customer_phone || q.phone || "",
    job_description: q.job_description || q.job || "",
    labour_cost: q.labour_cost || q.labour || 0,
    include_callout_charge: !!q.include_callout_charge || Number(q.callout_charge || 0) > 0,
    callout_charge: q.callout_charge || 0,
    include_travel_charge: !!q.include_travel_charge || Number(q.travel_charge || 0) > 0,
    travel_charge: q.travel_charge || 0,
    include_materials_handling: q.include_materials_handling !== false,
    materials_handling_percent: q.materials_handling_percent || 25,
    deposit_percent: q.deposit_percent || 0,
    materials: q.materials || q.material_lines || []
  };
}



function normaliseQuoteDataForEditing(data) {
  const root = data || {};
  const request = root.request || {};
  const result = root.result || {};
  const quote = root.quote || {};

  const q = {
    quote_type: request.quote_type || result.quote_type || quote.quote_type || root.quote_type || "small",
    lead_id: request.lead_id || root.lead_id || null,
    source_category: request.source_category || root.source_category || "",
    work_type: request.work_type || root.work_type || "",
    additional_work_types: request.additional_work_types || root.additional_work_types || [],
    customer_email: request.customer_email || root.customer_email || "",
    customer_name: request.customer_name || result.customer_name || quote.customer_name || root.customer_name || "",
    customer_address: request.customer_address || result.customer_address || quote.customer_address || root.customer_address || "",
    customer_phone: request.customer_phone || result.customer_phone || quote.customer_phone || root.customer_phone || "",
    job_description: request.job_description || result.job || result.job_description || quote.job_description || root.job_description || root.job || "",
    labour_cost: request.labour_cost || result.labour || quote.labour_cost || root.labour_cost || root.labour || 0,
    include_callout_charge: request.include_callout_charge !== undefined ? request.include_callout_charge : Number(result.callout_charge || 0) > 0,
    callout_charge: request.callout_charge || result.callout_charge || quote.callout_charge || root.callout_charge || 0,
    include_travel_charge: request.include_travel_charge !== undefined ? request.include_travel_charge : Number(result.travel_charge || 0) > 0,
    travel_charge: request.travel_charge || result.travel_charge || quote.travel_charge || root.travel_charge || 0,
    include_materials_handling: request.include_materials_handling !== undefined ? request.include_materials_handling : true,
    materials_handling_percent: request.materials_handling_percent || result.materials_handling_percent || quote.materials_handling_percent || root.materials_handling_percent || 25,
    deposit_percent: request.deposit_percent || result.deposit_percent || quote.deposit_percent || root.deposit_percent || 0,
    materials: request.materials || result.material_lines || quote.materials || root.materials || root.material_lines || []
  };

  q.materials = (q.materials || []).map(m => ({
    name: m.name || "",
    quantity: m.quantity || 1,
    supplier: m.supplier || "",
    url: m.url || "",
    manual_price: m.manual_price || m.full_unit_price || m.unit_price_used || m.price || 0,
    quote_charge_override: m.quote_charge_override,
    material_type: m.material_type || "chargeable",
    charge_method: m.charge_method || "full",
    quantity_source: m.quantity_source || "rule",
    learned_average_quantity: m.learned_average_quantity || null,
    learned_used_count: m.learned_used_count || null
  }));

  return q;
}

function safeSetValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value ?? "";
}

function safeSetChecked(id, value) {
  const el = document.getElementById(id);
  if (el) el.checked = !!value;
}

function populateInvoiceEditForm(item) {
  const invoice = item.invoice || {};
  document.getElementById("edit_invoice_customer_name").value = invoice.customer_name || "";
  document.getElementById("edit_invoice_customer_address").value = invoice.customer_address || "";
  document.getElementById("edit_invoice_customer_phone").value = invoice.customer_phone || "";
  document.getElementById("edit_invoice_job").value = invoice.job || "";
  document.getElementById("edit_invoice_job_reference").value = item.job_reference || invoice.job_reference || "";
  document.getElementById("edit_invoice_labour").value = invoice.labour || 0;
  document.getElementById("edit_invoice_callout_charge").value = invoice.callout_charge || item.quote_result?.callout_charge || 0;
  document.getElementById("edit_invoice_travel_charge").value = invoice.travel_charge || item.quote_result?.travel_charge || 0;
  document.getElementById("edit_invoice_materials").value = invoice.materials || 0;
  document.getElementById("edit_invoice_due_date").value = item.due_date || "";
  document.getElementById("edit_invoice_payment_link").value = item.payment_link || "";
  document.getElementById("edit_invoice_amount_paid").value = item.amount_paid || 0;
  document.getElementById("edit_invoice_reminder_email").value = item.reminder_email || "";
  document.getElementById("edit_invoice_reminders_enabled").checked = !!item.reminders_enabled;
}

function showInvoiceEditPanel(item) {
  CURRENT_EDITING_INVOICE_ID = item.id;
  const panel = document.getElementById("invoiceEditPanel");
  if (!panel) {
    alert("Invoice editor could not be found.");
    return;
  }

  // The editor was originally inside a tab panel. Move it directly under
  // document.body so it remains visible even while the Invoices tab is active.
  if (panel.parentElement !== document.body) {
    document.body.appendChild(panel);
  }

  populateInvoiceEditForm(item);
  panel.classList.remove("hidden");
  panel.style.display = "block";
  document.body.style.overflow = "hidden";

  window.setTimeout(() => {
    const ref = document.getElementById("edit_invoice_job_reference");
    if (ref) {
      ref.focus();
      ref.select();
    }
  }, 100);
}

function cancelInvoiceEdit() {
  CURRENT_EDITING_INVOICE_ID = null;
  const panel = document.getElementById("invoiceEditPanel");
  if (panel) {
    panel.classList.add("hidden");
    panel.style.display = "none";
  }
  document.body.style.overflow = "";
}

async function openInvoice(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data, false);
    document.getElementById("invoiceCard").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (e) {
    alert("Could not open invoice.");
  }
}

async function editInvoice(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not load invoice.");
    showInvoiceEditPanel(data);
    showNotice("Invoice loaded for editing.");
  } catch (e) {
    alert(e.message || "Could not load invoice for editing.");
  }
}

async function sendInvoiceWhatsApp(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    document.getElementById("invoiceWhatsappBtn").click();
  } catch (e) {
    alert("Could not open WhatsApp for this invoice.");
  }
}

function openInvoicePage(id) {
  window.open("/invoice/" + id, "_blank");
}

async function emailInvoice(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    document.getElementById("invoiceEmailBtn").click();
  } catch (e) {
    alert("Could not open email for this invoice.");
  }
}

async function saveInvoiceEdit() {
  if (!CURRENT_EDITING_INVOICE_ID) return;
  try {
    const payload = {
      customer_name: document.getElementById("edit_invoice_customer_name").value || "",
      customer_address: document.getElementById("edit_invoice_customer_address").value || "",
      customer_phone: document.getElementById("edit_invoice_customer_phone").value || "",
      job: document.getElementById("edit_invoice_job").value || "",
      job_reference: document.getElementById("edit_invoice_job_reference").value || "",
      labour: parseFloat(document.getElementById("edit_invoice_labour").value || 0),
      callout_charge: parseFloat(document.getElementById("edit_invoice_callout_charge").value || 0),
      travel_charge: parseFloat(document.getElementById("edit_invoice_travel_charge").value || 0),
      materials: parseFloat(document.getElementById("edit_invoice_materials").value || 0),
      due_date: document.getElementById("edit_invoice_due_date").value || "",
      payment_link: document.getElementById("edit_invoice_payment_link").value || "",
      amount_paid: parseFloat(document.getElementById("edit_invoice_amount_paid").value || 0),
      reminder_email: document.getElementById("edit_invoice_reminder_email").value || "",
      reminders_enabled: !!document.getElementById("edit_invoice_reminders_enabled").checked
    };

    const res = await fetch("/api/invoices/" + CURRENT_EDITING_INVOICE_ID, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    await loadInvoices();
    await loadCustomers();
    await loadDashboard();
    cancelInvoiceEdit();
    showNotice("Invoice updated. Job Ref saved.");
  } catch (e) {
    alert("Could not save invoice changes.");
  }
}

async function savePaymentLink(id) {
  try {
    const paymentLink = document.getElementById("payment_link_" + id).value || "";
    const res = await fetch("/api/invoices/" + id + "/payment-link", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ payment_link: paymentLink })
    });
    if (!res.ok) throw new Error();
    await loadInvoices();
    showNotice("Payment link saved.");
  } catch (e) {
    alert("Could not save payment link.");
  }
}

async function printInvoice(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    window.print();
  } catch (e) {
    alert("Could not print this invoice.");
  }
}

async function updateInvoicePaid(id) {
  try {
    const amount = parseFloat(document.getElementById("paid_" + id).value || 0);
    const res = await fetch("/api/invoices/" + id + "/status", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ status: "unpaid", amount_paid: amount })
    });
    if (!res.ok) throw new Error();
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice payment updated.");
  } catch (e) {
    alert("Could not update invoice.");
  }
}

async function markInvoicePaid(id, total) {
  try {
    const res = await fetch("/api/invoices/" + id + "/status", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ status: "paid", amount_paid: total })
    });
    if (!res.ok) throw new Error();
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice marked paid.");
  } catch (e) {
    alert("Could not mark invoice as paid.");
  }
}

async function markInvoiceUnpaid(id) {
  try {
    const res = await fetch("/api/invoices/" + id + "/status", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ status: "unpaid", amount_paid: 0 })
    });
    if (!res.ok) throw new Error();
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice marked unpaid.");
  } catch (e) {
    alert("Could not mark invoice as unpaid.");
  }
}

async function deleteInvoice(id) {
  if (!confirm("Delete this invoice?")) return;
  try {
    const res = await fetch("/api/invoices/" + id, { method: "DELETE" });
    if (!res.ok) throw new Error();
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice deleted.");
  } catch (e) {
    alert("Could not delete invoice.");
  }
}

toggleBathroomFields();
renderTemplates();
renderFavourites();
clearMaterials();
const initialMaterialSearchPanel = document.getElementById("manualMaterialSearchPanel");
if (initialMaterialSearchPanel) initialMaterialSearchPanel.style.display = "none";
setQuoteButtonMode(false);
updateLabourSuggestion();
renderTemplateButtons();
checkAIQuoteStatus();
renderMasterMaterialSuggestions();
loadDashboard();
loadHistory();
loadInvoices();
loadCustomers();
loadLeads();
