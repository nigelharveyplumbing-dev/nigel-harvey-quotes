"""Stage 6 local HTTP workflows against the same isolated app used by the browser."""

import base64
from email import message_from_string
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import smtplib
import subprocess
import unittest
from types import SimpleNamespace
from urllib.parse import urljoin
from unittest.mock import patch

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from PIL import Image
import requests

from local_browser_server import disposable_app


class _DivTreeParser(HTMLParser):
    """Track explicit div nesting without needing a browser or HTML dependency."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        if tag != "div":
            return
        attributes = dict(attrs)
        node = {
            "id": attributes.get("id", ""),
            "classes": set(attributes.get("class", "").split()),
            "parent": self.stack[-1] if self.stack else None,
            "children": [],
        }
        if node["parent"] is not None:
            node["parent"]["children"].append(node)
        self.nodes.append(node)
        self.stack.append(node)

    def handle_endtag(self, tag):
        if tag == "div" and self.stack:
            self.stack.pop()


class LocalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.username = secrets.token_urlsafe(16)
        cls.password = secrets.token_urlsafe(24)
        cls.sandbox = disposable_app(cls.username, cls.password)
        cls.app_module, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.app_module.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)
        token = base64.b64encode(f"{cls.username}:{cls.password}".encode()).decode()
        cls.auth = {"Authorization": "Basic " + token}

    def test_auth_public_pages_and_browser_shell(self):
        c = self.client
        self.assertEqual(c.get("/app").status_code, 401)
        self.assertEqual(c.get("/app").headers["www-authenticate"], "Basic")
        self.assertEqual(c.get("/app", headers={"Authorization": "Basic invalid"}).status_code, 401)
        self.assertEqual(c.get("/api/dashboard").status_code, 401)
        page = c.get("/app", headers=self.auth)
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="dashboardTab"', page.text)
        self.assertIn('id="quotesTab"', page.text)
        self.assertIn("function showTab", page.text)
        self.assertEqual(c.get("/api/dashboard", headers=self.auth).status_code, 200)
        for path in ("/", "/plumber-guildford", "/request-quote", "/robots.txt", "/sitemap.xml"):
            self.assertEqual(c.get(path).status_code, 200, path)
        self.assertEqual(c.get("/emergency-plumber-surrey").status_code, 200)
        self.assertEqual(c.get("/general-plumbing-surrey").status_code, 200)

    def test_invoice_card_payment_defaults_and_client_assets(self):
        """The default display matches server config without shipping payment literals."""
        source = Path(__file__).resolve().parents[1]
        settings = (source / "business" / "config.py").read_text()
        script = (source / "static" / "app.js").read_text()
        template = (source / "templates" / "app.html").read_text()
        defaults = {}
        for field, client_key in (
            ("BANK_NAME", "bank"),
            ("BANK_ACCOUNT_NAME", "accountName"),
            ("BANK_SORT_CODE", "sortCode"),
            ("BANK_ACCOUNT_NUMBER", "accountNumber"),
        ):
            server = re.search(rf'(?m)^{field} = .*? or "([^"]+)"', settings)
            self.assertIsNotNone(server, f"Missing default for {field}")
            defaults[client_key] = server.group(1)
            self.assertNotIn(server.group(1), script, f"Payment literal in JS: {field}")
            self.assertNotIn(server.group(1), template, f"Payment literal in HTML: {field}")
            self.assertIn(f"{client_key}: APP_PAYMENT_CONFIG.{client_key}", script)
        self.assertIn("window.CURRENT_INVOICE_PAYMENT_DETAILS = bankDetails", script)
        with disposable_app(self.username, self.password, bank_settings={}) as (m, _):
            with TestClient(m.app) as client:
                page = client.get("/app", headers=self.auth)
                self.assertEqual(page.status_code, 200)
                config = re.search(r'const APP_PAYMENT_CONFIG = (\{.*?\});', page.text)
                self.assertIsNotNone(config)
                self.assertTrue(json.loads(config.group(1)) == defaults,
                                "Default invoice display differs from server configuration")
                self.assertTrue(all(getattr(m, field) == defaults[key] for field, key in (
                    ("BANK_NAME", "bank"), ("BANK_ACCOUNT_NAME", "accountName"),
                    ("BANK_SORT_CODE", "sortCode"),
                    ("BANK_ACCOUNT_NUMBER", "accountNumber"))),
                    "Default configuration differs from invoice display")

    def test_synthetic_staging_payment_config_and_safe_embedding(self):
        page = self.client.get("/app", headers=self.auth)
        self.assertEqual(page.status_code, 200)
        config = re.search(r'const APP_PAYMENT_CONFIG = (\{.*?\});', page.text)
        self.assertIsNotNone(config)
        self.assertTrue(json.loads(config.group(1)) == {
            "bank": self.app_module.BANK_NAME,
            "accountName": self.app_module.BANK_ACCOUNT_NAME,
            "sortCode": self.app_module.BANK_SORT_CODE,
            "accountNumber": self.app_module.BANK_ACCOUNT_NUMBER,
        }, "Staging invoice display differs from configured payment data")
        self.assertEqual(self.client.get("/app").status_code, 401)
        injection = {'BANK_NAME': '</script><script>window.bad=1</script>'}
        with disposable_app(self.username, self.password, bank_settings=injection) as (m, _):
            with TestClient(m.app) as client:
                html = client.get("/app", headers=self.auth).text
                self.assertNotIn(injection["BANK_NAME"], html)
                config = re.search(r'const APP_PAYMENT_CONFIG = (\{.*?\});', html)
                self.assertIsNotNone(config)
                self.assertTrue(json.loads(config.group(1))["bank"] == injection["BANK_NAME"],
                                "Escaped payment configuration was altered")

    @unittest.skipUnless(shutil.which("node"), "Node is required to execute browser JavaScript")
    def test_copy_bank_details_uses_configured_staging_values(self):
        page = self.client.get("/app", headers=self.auth).text
        match = re.search(r'const APP_PAYMENT_CONFIG = (\{.*?\});', page)
        self.assertIsNotNone(match)
        script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('async function copyInvoiceBankDetails() {');
const end = source.indexOf('\nasync function sendCurrentOverdueReminder()', start);
if (start < 0 || end < 0) process.exit(2);
let copied = null;
const context = {
  window: { CURRENT_INVOICE_PAYMENT_DETAILS: {
    ...data, reference: 'INV-STAGING', amount: 12.5,
  } },
  navigator: { clipboard: { writeText: async value => { copied = value; } } },
  pounds: value => `£${Number(value).toFixed(2)}`,
  showNotice: () => {},
  prompt: () => { throw new Error('Unexpected clipboard fallback'); },
};
vm.runInNewContext(source.slice(start, end) + '\ncopyInvoiceBankDetails()', context)
  .then(() => {
    const expected = [
      `Bank: ${data.bank}`, `Account name: ${data.accountName}`,
      `Sort code: ${data.sortCode}`, `Account number: ${data.accountNumber}`,
      'Amount due: £12.50', 'Reference: INV-STAGING',
    ].join('\n');
    if (copied !== expected) process.exitCode = 1;
  }).catch(() => { process.exitCode = 1; });
"""
        result = subprocess.run(
            ["node", "-e", script, str(self.root / "static" / "app.js")],
            input=match.group(1), text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, "Copy action ignored staging payment configuration")

    @unittest.skipUnless(shutil.which("node"), "Node is required to execute browser JavaScript")
    def test_ai_draft_values_reach_generate_quote_payload_without_extra_manual_entry(self):
        """The AI build -> Generate Quote workflow must not silently submit empty fields."""
        script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const section = (start, end) => {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  if (first < 0 || last < 0) throw new Error(`Could not extract ${start}`);
  return source.slice(first, last);
};

const generateAI = section(
  'async function generateAIQuoteDraft() {',
  '\n\nfunction addQuoteHealthSuggestion('
);
const collectPayload = section(
  'function collectFormPayload() {',
  '\n\nfunction buildQuoteMaterialsWhatsappText('
);
const generateQuote = section(
  'async function generateQuote(options = {}) {',
  '\n\nasync function convertQuoteToInvoice('
);
const applyDraft = section(
  'function applyAIQuoteDraft() {',
  '\n\nfunction discardAIQuoteDraft('
);

const nodes = new Map();
const defaults = {
  quote_type: 'small', customer_name: 'Staging Test Customer',
  customer_address: '1 Test Street', customer_phone: '07000000000',
  job: 'Replace bath tap', labour: '', materials_handling_percent: '25',
  callout_charge: '200', travel_charge: '0', wall_tiling_m2: '0',
  floor_tiling_m2: '0', wall_height: 'half', deposit_percent: '0',
};
function element(id) {
  if (!nodes.has(id)) {
    nodes.set(id, {
      id, value: defaults[id] || '', checked: false, files: [], innerHTML: '',
      innerText: '', style: {}, classList: {add() {}, remove() {}},
    });
  }
  return nodes.get(id);
}

let materialRows = [];
let savedPayload = null;
let quoteRequests = 0;
const confirmations = [false, true];
const aiDraft = {
  scope_of_work: 'Replace bath tap and test for leaks.',
  labour_suggestion: 180,
  materials: [{
    name: 'Bath tap connectors', quantity: 2, supplier: 'Synthetic Supplier',
    manual_price: 12.5, required: true, display_status: 'required',
  }, {
    name: 'Optional decorative cover', quantity: 1, manual_price: 5,
    required: false, display_status: 'optional', include_in_quote: false,
  }, {
    name: 'Selected silicone', quantity: 1, manual_price: 3,
    required: false, display_status: 'optional', include_in_quote: true,
    optional_selected: true,
  }],
};

function materialRow(material) {
  return {
    querySelector(selector) {
      const fields = {
        '.m-name': material.name || '', '.m-qty': material.quantity || 1,
        '.m-supplier': material.supplier || '', '.m-url': material.url || '',
        '.m-manual': material.manual_price || 0,
      };
      return {value: fields[selector]};
    },
  };
}

const context = {
  console,
  document: {
    getElementById: element,
    querySelector: () => ({disabled: false, innerText: ''}),
    querySelectorAll(selector) {
      return selector === '.material-row' ? materialRows : [];
    },
  },
  fetch: async (url, options = {}) => {
    if (url === '/api/ai-quote-draft') {
      return {ok: true, json: async () => ({draft: aiDraft, context_summary: {}})};
    }
    if (url === '/api/quote') {
      quoteRequests += 1;
      savedPayload = JSON.parse(options.body);
      return {ok: true, json: async () => ({id: 1, result: {}})};
    }
    throw new Error(`Unexpected request: ${url}`);
  },
  quoteRequestCount: () => quoteRequests,
  currentMaterialsForAI: () => [],
  renderAIQuoteDraft: () => {},
  prepareDraftForV125: draft => draft,
  clearMaterials: () => { materialRows = []; },
  addMaterial: material => { materialRows.push(materialRow(material)); },
  isOptionalDraftMaterial: material => !material.required && material.display_status !== 'required',
  optionalMaterialIsSelected: material => material.include_in_quote === true || material.optional_selected === true,
  mergeDuplicateMaterialRowsInForm: () => {}, scheduleQuoteLearning: () => {},
  scheduleLabourIntelligence: () => {}, updateForgottenItemWarnings: () => {},
  updateSupplierPreferenceNotes: () => {},
  applyChargingRuleToMaterial: material => material,
  setEditingStatus: () => {}, setQuoteButtonMode: () => {},
  renderQuoteResult: () => {}, loadHistory: async () => {},
  loadCustomers: async () => {}, loadDashboard: async () => {},
  showNotice: () => {}, alert: () => {}, confirm: () => confirmations.shift(),
  escapeHtml: value => String(value || ''),
};
vm.createContext(context);
vm.runInContext(`
let SAVED_MATERIAL_DB = [{}];
let CURRENT_SITE_SURVEY = null;
let CAPTURED_SITE_PHOTOS = [];
let RECORDED_SITE_VIDEO = null;
let LAST_AI_QUOTE_DRAFT = null;
let AI_QUOTE_DRAFT_PENDING = false;
let CURRENT_QUOTE_ID = null;
let QUOTE_CREATE_IN_PROGRESS = false;

${generateAI}
${collectPayload}
${applyDraft}
${generateQuote}

globalThis.runWorkflow = async () => {
  await generateAIQuoteDraft();
  await generateQuote({skipDashboardReload: true});
  if (quoteRequestCount() !== 0) {
    throw new Error('Generate Quote submitted after the pending AI draft was declined');
  }
  await generateQuote({skipDashboardReload: true});
};
`, context);

context.runWorkflow().then(() => {
  if (!savedPayload) throw new Error('Generate Quote did not submit a payload');
  if (savedPayload.labour_cost !== 180) {
    throw new Error(`AI labour was lost: ${savedPayload.labour_cost}`);
  }
  if (savedPayload.materials.length !== 2 || savedPayload.materials[0].manual_price !== 12.5 ||
      savedPayload.materials[1].name !== 'Selected silicone') {
    throw new Error(`AI materials were lost: ${JSON.stringify(savedPayload.materials)}`);
  }
}).catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
"""
        result = subprocess.run(
            ["node", "-e", script, str(self.root / "static" / "app.js")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(
            result.returncode, 0,
            "AI draft values did not reach Generate Quote: " + (result.stderr or result.stdout),
        )

    @unittest.skipUnless(shutil.which("node"), "Node is required to execute browser JavaScript")
    def test_generate_quote_double_click_sends_one_create_request(self):
        """Hold the first response open: the second click must not create another quote."""
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const first = source.indexOf('async function generateQuote(options = {}) {');
const last = source.indexOf('\n\nasync function convertQuoteToInvoice(', first);
assert.ok(first >= 0 && last > first);
const button = { disabled: false, innerText: 'Generate Quote' };
const errorBox = { style: { display: 'none' }, innerText: '' };
const calls = [];
let resolveRequest;
const context = {
  document: {
    getElementById: () => errorBox,
    querySelector: () => button,
  },
  collectFormPayload: () => ({customer_name: 'Synthetic Customer'}),
  setEditingStatus: () => {},
  setQuoteButtonMode: editing => { button.innerText = editing ? 'Update Quote' : 'Generate Quote'; },
  renderQuoteResult: () => {},
  showNotice: () => {},
  fetch: async (url, options) => {
    calls.push(`${options.method} ${url}`);
    return await new Promise(resolve => { resolveRequest = resolve; });
  },
};
vm.createContext(context);
vm.runInContext(`
let CURRENT_QUOTE_ID = null;
let QUOTE_CREATE_IN_PROGRESS = false;
let AI_QUOTE_DRAFT_PENDING = false;
let LAST_AI_QUOTE_DRAFT = null;
${source.slice(first, last)}
globalThis.generateQuoteForTest = generateQuote;
globalThis.resetQuoteForTest = () => { CURRENT_QUOTE_ID = null; };
`, context);

(async () => {
  const firstSave = context.generateQuoteForTest({skipDashboardReload: true});
  const repeatedClick = context.generateQuoteForTest({skipDashboardReload: true});
  assert.deepEqual(calls, ['POST /api/quote']);
  assert.equal(button.disabled, true);
  assert.equal(await repeatedClick, null);
  resolveRequest({ok: true, json: async () => ({id: 42, result: {}})});
  await firstSave;
  assert.equal(button.disabled, false);
  assert.equal(button.innerText, 'Update Quote');

  const update = context.generateQuoteForTest({skipDashboardReload: true});
  assert.deepEqual(calls, ['POST /api/quote', 'PUT /api/quotes/42']);
  resolveRequest({ok: true, json: async () => ({id: 42, result: {}})});
  await update;

  context.resetQuoteForTest();
  const failedSave = context.generateQuoteForTest({skipDashboardReload: true});
  assert.equal(button.disabled, true);
  resolveRequest({ok: false});
  assert.equal(await failedSave, null);
  assert.equal(button.disabled, false);
  assert.equal(button.innerText, 'Generate Quote');
  const retry = context.generateQuoteForTest({skipDashboardReload: true});
  assert.deepEqual(calls, ['POST /api/quote', 'PUT /api/quotes/42', 'POST /api/quote', 'POST /api/quote']);
  resolveRequest({ok: true, json: async () => ({id: 43, result: {}})});
  await retry;
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        result = subprocess.run(
            ["node", "-e", script, str(self.root / "static" / "app.js")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node is required to execute browser JavaScript")
    def test_recent_quote_links_show_customer_and_value(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
function section(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first);
  return source.slice(first, last);
}
const code = section('function pounds(value) {', '\n\nfunction escapeHtml(')
  + section('function escapeHtml(text) {', '\n\nfunction showNotice(')
  + section('function renderRecentQuotes(items) {', '\n\nfunction renderBusinessReport(')
  + '\nglobalThis.render = renderRecentQuotes;';
const context = {};
vm.runInNewContext(code, context);
const html = context.render([{id: 2, customer_name: 'Nigel & Sam', total_price: 125.5},
                             {id: 3, customer_name: '<script>', total_price: 40}]);
assert.match(html, /loadSavedQuote\(2\).*#2 · Nigel &amp; Sam · £125\.50/);
assert.match(html, /loadSavedQuote\(3\).*#3 · &lt;script&gt; · £40\.00/);
assert.equal(context.render([]), 'None');
"""
        result = subprocess.run(
            ["node", "-e", script, str(self.root / "static" / "app.js")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node is required to execute browser JavaScript")
    def test_invoice_preview_button_brings_rendered_card_into_view(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
function section(start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first);
  return source.slice(first, last);
}
const code = section('function renderInvoiceCard(item, scrollToTop = true) {',
                     '\n\nfunction downloadCurrentQuotePdf(')
  + section('async function loadInvoices() {', '\n\nfunction renderQuoteStatus(')
  + section('async function openInvoice(id) {', '\n\nasync function editInvoice(')
  + '\nglobalThis.preview = openInvoice; globalThis.list = loadInvoices;'
  + '\nglobalThis.currentId = () => CURRENT_INVOICE_ID;';
const events = [], nodes = {};
const document = {getElementById(id) {
  return nodes[id] ||= {
    style: {}, classList: {toggle() {}}, innerText: '', innerHTML: '', href: '',
    scrollIntoView(options) {events.push({id, options});}
  };
}};
const invoice = {
  id: 3, invoice_number: 'INV-2026-0003', created_at: '2026-09-29',
  status: 'unpaid', total_price: 125, amount_paid: 0, balance_due: 125,
  invoice: {customer_name: 'Test customer', customer_phone: '07000000000', job: 'Test job'},
  quote_result: {quote_type: 'small'}, photos: [],
};
const context = {
  document, window: {location: {origin: 'https://staging.example'},
                     scrollTo() {events.push('top');}},
  fetch: async url => ({ok: true, json: async () => url === '/api/invoices' ? [invoice] : invoice}),
  renderStatusBadge: () => 'Unpaid', renderInvoicePhotoGallery() {},
  cancelInvoiceEdit() {}, normalisePhone: () => '',
  escapeHtml: value => String(value || ''), pounds: value => '£' + Number(value || 0).toFixed(2),
  APP_PAYMENT_CONFIG: {bank: 'Test bank', accountName: 'Test', sortCode: '00-00-00', accountNumber: '00000000'},
  alert(message) {throw new Error(message);}, CURRENT_INVOICE_ID: null, SAVED_INVOICES: [],
};
vm.createContext(context);
vm.runInContext(code, context);
(async () => {
  await context.list();
  assert.match(nodes.invoiceList.innerHTML, /onclick="openInvoice\(3\)">Preview Invoice<\/button>/);
  await context.preview(3);
  assert.equal(context.currentId(), 3);
  assert.equal(nodes.invoiceCard.style.display, 'block');
  assert.equal(nodes.i_number.innerText, 'INV-2026-0003');
  assert.equal(nodes.invoiceOpenBtn.href, 'https://staging.example/invoice/3');
  assert.deepEqual(JSON.parse(JSON.stringify(events)),
                   [{id: 'invoiceCard', options: {behavior: 'smooth', block: 'start'}}]);
  assert.equal([...source.matchAll(/onclick="openInvoice\(\$\{i\.id\}\)">Preview Invoice<\/button>/g)].length, 2);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
        result = subprocess.run(
            ["node", "-e", script, str(self.root / "static" / "app.js")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_quote_and_invoice_cards_are_not_nested_inside_flex_headers(self):
        """Malformed div nesting makes the document cards collapse into narrow columns."""
        parser = _DivTreeParser()
        parser.feed((self.root / "templates" / "app.html").read_text())
        by_id = {node["id"]: node for node in parser.nodes if node["id"]}

        quote = by_id["resultCard"]
        invoice = by_id["invoiceCard"]
        quote_header = next(node for node in quote["children"] if "quote-header" in node["classes"])
        invoice_header = next(node for node in invoice["children"] if "quote-header" in node["classes"])

        self.assertTrue(
            any("doc-grid-two" in node["classes"] for node in quote["children"]),
            "Quote details grid is trapped inside the horizontal flex header",
        )
        self.assertIsNot(
            invoice["parent"], quote,
            "Invoice card is incorrectly nested inside the quote card",
        )
        self.assertFalse(
            any("doc-grid-two" in node["classes"] for node in quote_header["children"]),
            "Quote content is rendered as flex-header columns",
        )
        self.assertFalse(
            any("doc-grid-two" in node["classes"] for node in invoice_header["children"]),
            "Invoice content is rendered as flex-header columns",
        )

    def test_quote_invoice_customer_documents_and_deletion(self):
        c = self.client
        payload = self.app_module.QuoteRequest(
            customer_name="Synthetic Browser Customer", customer_address="1 Test Lane",
            customer_phone="07000000000", job_description="Replace test valve",
            labour_cost=100.10,
            materials=[self.app_module.MaterialItem(name="Test valve", quantity=2, manual_price=10)],
        ).model_dump()
        created = c.post("/api/quote", headers=self.auth, json=payload)
        self.assertEqual(created.status_code, 200)
        quote = created.json()
        self.assertEqual(quote["result"]["total_price"], 125.10)
        quote_id = quote["id"]
        self.assertEqual(c.get(f"/api/quotes/{quote_id}").status_code, 401)
        self.assertEqual(c.get(f"/api/quotes/{quote_id}/pdf").status_code, 200)
        self.assertEqual(c.get(f"/api/quotes/{quote_id}/pdf").content[:4], b"%PDF")
        payload["labour_cost"] = 120.20
        edited = c.put(f"/api/quotes/{quote_id}", headers=self.auth, json=payload)
        self.assertEqual(edited.json()["result"]["total_price"], 145.20)
        invoice = c.post(f"/api/quotes/{quote_id}/to-invoice", headers=self.auth).json()
        invoice_id = invoice["id"]
        customer_id = quote["customer_id"]
        self.assertEqual(invoice["quote_id"], quote_id)
        self.assertEqual(invoice["invoice"]["customer_name"], payload["customer_name"])
        self.assertEqual(c.get(f"/api/invoices/{invoice_id}").status_code, 401)
        self.assertEqual(c.get(f"/invoice/{invoice_id}").status_code, 200)
        self.assertEqual(c.get(f"/api/invoices/{invoice_id}/pdf").content[:4], b"%PDF")
        self.assertEqual(c.get(f"/api/invoices/{invoice_id}/payment-qr").status_code, 200)
        history = c.get(f"/api/customers/{customer_id}/history", headers=self.auth).json()
        self.assertTrue(history["quotes"])
        self.assertTrue(history["invoices"])
        self.assertIn("Synthetic Browser Customer", str(c.get("/api/customers", headers=self.auth).json()))
        edit = self.app_module.InvoiceEditRequest(
            customer_name=payload["customer_name"], customer_address=payload["customer_address"],
            customer_phone=payload["customer_phone"], job=payload["job_description"],
            job_reference="LOCAL-1", labour=120.20, materials=25,
            due_date=invoice["due_date"], payment_link="https://example.test/pay",
        ).model_dump()
        self.assertEqual(c.put(f"/api/invoices/{invoice_id}", headers=self.auth,
                               json=edit).json()["job_reference"], "LOCAL-1")
        status = c.post(f"/api/invoices/{invoice_id}/status", headers=self.auth,
                        json={"status": "part paid", "amount_paid": 20}).json()
        self.assertEqual(status["balance_due"], 125.20)
        self.assertEqual(c.delete(f"/api/invoices/{invoice_id}", headers=self.auth).status_code, 200)
        self.assertEqual(c.delete(f"/api/quotes/{quote_id}", headers=self.auth).status_code, 200)
        self.assertEqual(c.delete(f"/api/customers/{customer_id}", headers=self.auth).status_code, 200)

    def test_lead_material_and_synthetic_photo_workflow(self):
        c = self.client
        lead = c.post("/api/leads", json={"name": "Synthetic Lead", "phone": "07000000000",
                                           "description": "Test tap"})
        self.assertEqual(lead.status_code, 200)
        lead_id = lead.json()["id"]
        self.assertEqual(c.get("/api/leads").status_code, 401)
        self.assertEqual(c.put(f"/api/leads/{lead_id}/status", headers=self.auth,
                               json={"status": "contacted"}).status_code, 200)
        self.assertEqual(c.delete(f"/api/leads/{lead_id}", headers=self.auth).status_code, 200)

        self.app_module.upsert_material_price_cache("https://example.test/local-valve",
                                                   "Local valve", "Synthetic Supplier", price=5)
        prices = c.get("/api/material-prices", headers=self.auth).json()
        material_id = next(row["id"] for row in prices if row["name"] == "Local valve")
        self.assertEqual(c.get("/api/material-search?q=valve", headers=self.auth).status_code, 200)
        self.assertEqual(c.put(f"/api/material-prices/{material_id}", headers=self.auth,
                               json={"name": "Local valve", "supplier": "Synthetic Supplier",
                                     "url": "https://example.test/local-valve", "manual_price": 7.25}).status_code, 200)
        self.assertEqual(c.delete(f"/api/material-prices/{material_id}", headers=self.auth).status_code, 200)

        payload = self.app_module.QuoteRequest(customer_name="Synthetic Photo Customer",
                                               job_description="Photo test", labour_cost=10).model_dump()
        quote = c.post("/api/quote", headers=self.auth, json=payload).json()
        invoice = c.post(f"/api/quotes/{quote['id']}/to-invoice", headers=self.auth).json()
        invoice_id = invoice["id"]
        picture = Image.new("RGB", (16, 16), "blue")
        image_bytes = io.BytesIO()
        picture.save(image_bytes, format="PNG")
        uploaded = c.post(f"/api/invoices/{invoice_id}/photos", headers=self.auth,
                          data={"category": "after", "caption": "Synthetic installation"},
                          files={"photos": ("sample.png", image_bytes.getvalue(), "image/png")})
        self.assertEqual(uploaded.status_code, 200)
        photo = uploaded.json()["photos"][0]
        self.assertEqual(c.get(photo["url"]).headers["content-type"], "image/jpeg")
        self.assertTrue((self.root / "photos" / str(invoice_id) / photo["filename"]).exists())
        self.assertEqual(c.delete(photo["url"], headers=self.auth).status_code, 200)
        self.assertFalse((self.root / "photos" / str(invoice_id) / photo["filename"]).exists())

    def test_network_and_smtp_are_blocked(self):
        self.assertTrue(self.app_module.DB_PATH.is_relative_to(self.root))
        self.assertNotEqual(str(self.app_module.DB_PATH), "/var/data/quotes.db")
        self.assertIn("accountName: APP_PAYMENT_CONFIG.accountName",
                      (self.root / "static" / "app.js").read_text())
        with self.assertRaisesRegex(RuntimeError, "External HTTP blocked"):
            requests.get("https://example.test")
        with self.assertRaisesRegex(RuntimeError, "External DNS blocked"):
            socket.getaddrinfo("example.test", 443)
        with self.assertRaisesRegex(RuntimeError, "SMTP blocked"):
            smtplib.SMTP_SSL("example.test")

    def test_default_invoice_link_still_uses_live_domain(self):
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": "", "APP_ENVIRONMENT": ""}):
            self.assertEqual(self.app_module.build_invoice_public_url(1),
                             "https://www.nigelharveyplumbing.co.uk/invoice/1")

    def test_default_absolute_document_and_website_urls(self):
        m = self.app_module
        base = "https://www.nigelharveyplumbing.co.uk"
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": "", "APP_ENVIRONMENT": ""}):
            self.assertEqual(m.get_public_base_url(), base)
            for path in ("/invoice/47", "/api/invoices/47/pdf",
                         "/api/quotes/12/pdf", "/api/invoices/47/payment-qr"):
                self.assertEqual(m.absolute_url(path), base + path)
            self.assertEqual(m.build_invoice_public_url(47), base + "/invoice/47")
            home = self.client.get("/").text
            self.assertIn(f'<link rel="canonical" href="{base}/">', home)
            self.assertIn(f'<meta property="og:url" content="{base}/">', home)
            self.assertIn(f'<link rel="canonical" href="{base}/request-quote">',
                          self.client.get("/request-quote").text)
            self.assertIn(base + "/plumber-guildford", self.client.get("/plumber-guildford").text)
            self.assertIn(base + "/sitemap.xml", self.client.get("/robots.txt").text)
            self.assertIn(base + "/plumber-guildford", self.client.get("/sitemap.xml").text)

    def test_default_invoice_and_lead_email_url(self):
        m = self.app_module
        item = {
            "id": 47, "invoice_number": "INV-TEST-47", "job_reference": "JOB-47",
            "invoice": {"customer_name": "Synthetic Customer"}, "status": "unpaid",
            "balance_due": 12.5,
        }
        context = SimpleNamespace(
            build_invoice_public_url=m.build_invoice_public_url,
            company_name="Test company", company_phone="000", company_email="test@example.test",
            pounds_text=m.pounds_text, get_company_logo_value=lambda: "",
            generate_invoice_pdf_bytes=lambda _: b"%PDF-synthetic",
            from_header="Test sender <sender@example.test>",
        )
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": "", "APP_ENVIRONMENT": ""}):
            invoice_msg = m.document_sharing.prepare_invoice_email(
                item, "recipient@example.test", "", context)
            plain = next(p for p in invoice_msg.walk() if p.get_content_type() == "text/plain")
            self.assertIn("Invoice link: https://www.nigelharveyplumbing.co.uk/invoice/47",
                          plain.get_payload(decode=True).decode())
            with patch.object(m, "EMAIL_ENABLED", True), \
                 patch.object(m, "EMAIL_USER", "sender@example.test"), \
                 patch.object(m, "EMAIL_PASS", "test-only"), \
                 patch.object(m.smtplib, "SMTP_SSL") as smtp:
                m.send_lead_notification_email({"name": "Synthetic Lead"})
                raw = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
            lead_msg = message_from_string(raw)
            lead_plain = next(p for p in lead_msg.walk() if p.get_content_type() == "text/plain")
            self.assertIn("Open app: \n", lead_plain.get_payload(decode=True).decode())

    def test_staging_document_and_website_urls_stay_on_staging_origin(self):
        m = self.app_module
        stage = "https://quotes-stage.example.test"
        production = "https://www.nigelharveyplumbing.co.uk"
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": f"  {stage}///  ",
                                     "APP_ENVIRONMENT": "staging"}):
            self.assertEqual(m.get_public_base_url(), stage)
            paths = ("/invoice/47", "/api/invoices/47/pdf", "/api/quotes/12/pdf",
                     "/api/invoices/47/payment-qr", "/api/invoices/47/photos/3")
            for path in paths:
                with self.subTest(path=path):
                    self.assertEqual(m.absolute_url(path), stage + path)
                    self.assertNotIn(production, m.absolute_url(path))
            self.assertEqual(m.absolute_url("invoice/47"), stage + "/invoice/47")
            self.assertEqual(m.build_invoice_public_url(47), stage + "/invoice/47")

            for page in ("/", "/new-home", "/plumber-guildford", "/emergency-plumber-guildford",
                         "/request-quote", "/robots.txt", "/sitemap.xml"):
                response = self.client.get(page, headers=self.auth)
                self.assertEqual(response.status_code, 200, page)
                self.assertNotIn(production, response.text, page)
            home = self.client.get("/", headers=self.auth).text
            self.assertIn(f'<link rel="canonical" href="{stage}/">', home)
            self.assertIn(f'<meta property="og:url" content="{stage}/">', home)
            self.assertIn("Disallow: /", self.client.get("/robots.txt", headers=self.auth).text)
            self.assertIn(stage + "/plumber-guildford",
                          self.client.get("/sitemap.xml", headers=self.auth).text)
            self.assertIn(stage + "/emergency-plumber-surrey",
                          m.render_service_page(m.SERVICE_PAGES[0], ""))

            payload = m.QuoteRequest(customer_name="Stage Link Customer", labour_cost=10).model_dump()
            quote = self.client.post("/api/quote", headers=self.auth, json=payload).json()
            invoice = self.client.post(f"/api/quotes/{quote['id']}/to-invoice",
                                       headers=self.auth).json()
            invoice_page = self.client.get(f"/invoice/{invoice['id']}", headers=self.auth).text
            for relative in (f"/api/invoices/{invoice['id']}/pdf",
                             f"/api/invoices/{invoice['id']}/payment-qr"):
                self.assertIn(relative, invoice_page)
                self.assertEqual(urljoin(stage + "/", relative), stage + relative)
            self.assertNotIn(production, invoice_page)

    def test_staging_invoice_email_and_lead_notification_urls(self):
        m = self.app_module
        stage = "https://quotes-stage.example.test"
        item = {"id": 47, "invoice_number": "INV-STAGE-47", "job_reference": "JOB-47",
                "invoice": {"customer_name": "Synthetic Customer"}, "status": "unpaid",
                "balance_due": 12.5}
        context = SimpleNamespace(
            build_invoice_public_url=m.build_invoice_public_url,
            company_name="Test company", company_phone="000", company_email="test@example.test",
            pounds_text=m.pounds_text, get_company_logo_value=lambda: "",
            generate_invoice_pdf_bytes=lambda _: b"%PDF-synthetic",
            from_header="Test sender <sender@example.test>",
        )
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": stage + "/",
                                     "APP_ENVIRONMENT": "staging"}):
            invoice_msg = m.document_sharing.prepare_invoice_email(
                item, "recipient@example.test", "", context)
            plain = next(p for p in invoice_msg.walk() if p.get_content_type() == "text/plain")
            html = next(p for p in invoice_msg.walk() if p.get_content_type() == "text/html")
            self.assertIn("Invoice link: " + stage + "/invoice/47",
                          plain.get_payload(decode=True).decode())
            self.assertIn('href="' + stage + '/invoice/47"', html.get_payload(decode=True).decode())
            with patch.object(m, "EMAIL_ENABLED", True), \
                 patch.object(m, "EMAIL_USER", "sender@example.test"), \
                 patch.object(m, "EMAIL_PASS", "test-only"), \
                 patch.object(m.smtplib, "SMTP_SSL") as smtp:
                m.send_lead_notification_email({"name": "Synthetic Lead"})
                raw = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
            lead_msg = message_from_string(raw)
            lead_plain = next(p for p in lead_msg.walk() if p.get_content_type() == "text/plain")
            self.assertIn("Open app: " + stage + "\n", lead_plain.get_payload(decode=True).decode())

    def test_staging_origin_configuration_fails_closed(self):
        m = self.app_module
        for configured in ("", "https://www.nigelharveyplumbing.co.uk/",
                           "https://nigelharveyplumbing.co.uk", "not-a-url",
                           "https://quotes-stage.example.test/path",
                           "https://quotes-stage.example.test?redirect=live",
                           "https://quotes-stage.example.test:badport"):
            with self.subTest(origin=configured), \
                 patch.dict(os.environ, {"APP_ENVIRONMENT": "staging",
                                          "PUBLIC_BASE_URL": configured}):
                with self.assertRaises(ValueError):
                    m.get_public_base_url()

    def test_staging_startup_rejects_missing_origin(self):
        with self.assertRaisesRegex(ValueError, "required in staging"):
            with disposable_app(self.username, self.password, environment="staging"):
                self.fail("Staging app started without PUBLIC_BASE_URL")

    def test_explicit_production_origin_matches_default(self):
        production = "https://www.nigelharveyplumbing.co.uk"
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": production + "/",
                                     "APP_ENVIRONMENT": "production"}):
            self.assertEqual(self.app_module.get_public_base_url(), production)
            self.assertEqual(self.app_module.build_invoice_public_url(47),
                             production + "/invoice/47")
            self.assertIn(f'href="{production}/"', self.client.get("/").text)

    def test_apex_production_override_is_normalized_to_www(self):
        production = "https://www.nigelharveyplumbing.co.uk"
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://nigelharveyplumbing.co.uk",
                                     "APP_ENVIRONMENT": "production"}):
            self.assertEqual(self.app_module.get_public_base_url(), production)
            for path in ("/", "/plumber-guildford", "/general-plumbing-surrey",
                         "/request-quote"):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    soup = BeautifulSoup(response.text, "html.parser")
                    canonical = soup.select_one('link[rel="canonical"]')
                    if canonical:
                        self.assertTrue(canonical["href"].startswith(production))
                    og_url = soup.select_one('meta[property="og:url"]')
                    if og_url:
                        self.assertTrue(og_url["content"].startswith(production))
                    for script in soup.select('script[type="application/ld+json"]'):
                        self.assertNotIn("https://nigelharveyplumbing.co.uk",
                                         json.dumps(json.loads(script.text)))
            self.assertIn(production + "/sitemap.xml", self.client.get("/robots.txt").text)
            self.assertIn(production + "/plumber-guildford",
                          self.client.get("/sitemap.xml").text)


class StagingAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.username = secrets.token_urlsafe(16)
        cls.password = secrets.token_urlsafe(24)
        cls.sandbox = disposable_app(
            cls.username, cls.password, environment="staging",
            public_base_url="https://synthetic-stage.example.test",
        )
        cls.app_module, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.app_module.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)
        def header(password):
            encoded = base64.b64encode(f"{cls.username}:{password}".encode()).decode()
            return {"Authorization": "Basic " + encoded}
        cls.auth = header(cls.password)
        cls.wrong_auth = header(cls.password + "-wrong")

    def test_all_routes_and_framework_pages_reject_before_side_effects(self):
        m = self.app_module
        routes = [(method, route) for route in m.app.routes
                  if route.path not in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
                  for method in getattr(route, "methods", [])]
        self.assertEqual(len(routes), 81)
        parameters = {"invoice_id": "1", "quote_id": "1", "customer_id": "1",
                      "lead_id": "1", "appointment_id": "1", "job_id": "1",
                      "material_id": "1", "photo_id": "1", "filename": "sample.db",
                      "area_slug": "guildford", "service_slug": "plumber"}

        def file_state():
            return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.root.rglob("*") if p.is_file()}

        with patch.object(m, "get_db", side_effect=AssertionError("database reached")), \
             patch.object(m.smtplib, "SMTP_SSL", side_effect=AssertionError("SMTP reached")), \
             patch.object(m.requests, "get", side_effect=AssertionError("external GET reached")), \
             patch.object(m.requests, "post", side_effect=AssertionError("external POST reached")):
            before = file_state()
            for method, route in routes:
                path = route.path.format(**parameters)
                with self.subTest(method=method, path=route.path), patch.object(
                    route.dependant, "call", side_effect=AssertionError("handler reached")
                ):
                    for headers in ({}, self.wrong_auth):
                        response = self.client.request(method, path, headers=headers)
                        self.assertEqual(response.status_code, 401)
                        self.assertEqual(response.headers.get("www-authenticate"), "Basic")
            for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
                self.assertEqual(self.client.get(path).status_code, 401)
            self.assertEqual(file_state(), before)

    def test_authenticated_staging_website_enquiry_and_documents(self):
        c = self.client
        for path in ("/", "/request-quote", "/plumber-guildford", "/sitemap.xml", "/app"):
            self.assertEqual(c.get(path, headers=self.auth).status_code, 200, path)
            self.assertEqual(c.get(path).status_code, 401, path)
        robots = c.get("/robots.txt", headers=self.auth)
        self.assertEqual(robots.status_code, 200)
        self.assertIn("Disallow: /", robots.text)
        self.assertNotIn("Allow: /", robots.text)
        self.assertEqual(c.get("/robots.txt").status_code, 401)
        self.assertEqual(c.get("/api/dashboard", headers=self.auth).status_code, 200)
        lead_data = {"name": "Synthetic Stage Lead", "phone": "07000000000",
                     "description": "Test tap"}
        self.assertEqual(c.post("/api/leads", json=lead_data).status_code, 401)
        self.assertEqual(c.post("/api/leads", headers=self.wrong_auth,
                                json=lead_data).status_code, 401)
        self.assertEqual(c.post("/api/leads", headers=self.auth, json=lead_data).status_code, 200)
        payload = self.app_module.QuoteRequest(customer_name="Synthetic Stage Customer",
                                               labour_cost=10).model_dump()
        quote = c.post("/api/quote", headers=self.auth, json=payload).json()
        invoice = c.post(f"/api/quotes/{quote['id']}/to-invoice", headers=self.auth).json()
        for path in (f"/invoice/{invoice['id']}",
                     f"/api/invoices/{invoice['id']}/pdf",
                     f"/api/invoices/{invoice['id']}/payment-qr",
                     f"/api/quotes/{quote['id']}/pdf"):
            self.assertEqual(c.get(path).status_code, 401, path)
            self.assertEqual(c.get(path, headers=self.wrong_auth).status_code, 401, path)
            self.assertEqual(c.get(path, headers=self.auth).status_code, 200, path)

    def test_explicit_production_mode_keeps_public_routes(self):
        with disposable_app(self.username, self.password, environment="production") as (m, _):
            with TestClient(m.app) as c:
                for path in ("/", "/request-quote", "/robots.txt", "/sitemap.xml"):
                    self.assertEqual(c.get(path).status_code, 200, path)
                self.assertIn("Allow: /", c.get("/robots.txt").text)
                self.assertEqual(c.post("/api/leads", json={
                    "name": "Synthetic Public Lead", "description": "Test enquiry",
                }).status_code, 200)
                self.assertEqual(c.get("/app").status_code, 401)
                self.assertEqual(c.get("/api/quotes").status_code, 401)


if __name__ == "__main__":
    unittest.main()
