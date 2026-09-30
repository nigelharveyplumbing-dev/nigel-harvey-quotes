const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const MaterialSelection = require('../static/material_selection.js');

const rows = [
  {name:'Thomas Dudley Niagara Dual-Flush Valve', supplier:'City Plumbing',
    url:'https://example.test/niagara', last_manual_price:42.5},
  {name:'Fluidmaster Dual-Flush Valve', supplier:'Screwfix',
    url:'https://example.test/fluidmaster', last_live_price:24.99},
  {name:'Dual-Flush Valve Button', supplier:'Screwfix', last_price:14.99},
];
const generic = MaterialSelection.review('dual-flush valve', 'I need a dual-flush valve.', rows);
assert.equal(generic.status, 'choose');
assert.equal(generic.selected, null);
assert.deepEqual(generic.choices.map(x => x.name), [rows[1].name, rows[0].name]);
assert.equal(generic.choices[0].price, 24.99);
assert.equal(generic.choices[1].supplier, 'City Plumbing');
assert.equal(MaterialSelection.candidates('2 inch dual-flush valve', [
  {name:'1.5 inch dual-flush valve with 2 inch outlet', last_price:20}]).length, 0);

const exact = MaterialSelection.review('Thomas Dudley Niagara dual-flush valve',
  'Use the Thomas Dudley Niagara dual-flush valve.', rows);
assert.equal(exact.status, 'selected');
assert.equal(exact.selected.name, rows[0].name);
assert.equal(exact.selected.price, 42.5);

const unique = MaterialSelection.review('15mm Endfeed Elbow', 'I need a 15mm endfeed elbow.',
  [{name:'15mm Endfeed Elbow', supplier:'Toolstation', last_price:1.2}]);
assert.equal(unique.status, 'selected');
assert.equal(unique.selected.supplier, 'Toolstation');

const absent = MaterialSelection.review('macerator pump', 'I need a macerator pump.', rows);
assert.equal(absent.status, 'unmatched');
assert.equal(absent.selected, null);
assert.equal(absent.choices.length, 0);

// Exercise the actual draft reconciliation and choice handler without loading
// unrelated UI startup code or submitting a quote.
const app = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const code = app.slice(app.indexOf('function reconcileRequiredSurveyMaterials('),
  app.indexOf('function materialAliasInfo('));
let currentDraft;
const context = {
  MaterialSelection, SAVED_MATERIAL_DB: rows,
  CURRENT_SITE_SURVEY: {transcript:'I need a dual-flush valve.', material_actions:[
    {action:'include_required', material_name:'dual-flush valve'}]},
  canonicalMaterialName: x => x.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(),
  LAST_AI_QUOTE_DRAFT: null,
  renderAIQuoteDraft: x => { currentDraft = x.draft; },
  document: {getElementById: () => null},
};
vm.createContext(context);
vm.runInContext(code, context);
const draft = {materials:[{name:rows[0].name, original_rule_name:'dual-flush valve',
  supplier:rows[0].supplier, url:rows[0].url, manual_price:42.5, required:true}]};
context.reconcileRequiredSurveyMaterials(draft);
assert.equal(draft.materials[0].name, 'dual-flush valve');
assert.equal(draft.materials[0].manual_price, 0);
assert.equal(draft.materials[0].url, '');
assert.equal(draft.materials[0].material_review.status, 'choose');
context.LAST_AI_QUOTE_DRAFT = draft;
context.chooseDraftMaterial(0, 1);
assert.equal(currentDraft.materials[0].name, rows[0].name);
assert.equal(currentDraft.materials[0].manual_price, 42.5);
assert.equal(currentDraft.materials[0].supplier, 'City Plumbing');
context.reconcileRequiredSurveyMaterials(currentDraft);
assert.equal(currentDraft.materials[0].name, rows[0].name);
assert.equal(currentDraft.materials[0].manual_price, 42.5);

const applied = [];
Object.assign(context, {
  prepareDraftForV125: x => context.reconcileRequiredSurveyMaterials(x),
  clearMaterials: () => {}, addMaterial: x => applied.push(x),
  isOptionalDraftMaterial: () => false, optionalMaterialIsSelected: () => true,
  mergeDuplicateMaterialRowsInForm: () => {}, scheduleQuoteLearning: () => {},
  scheduleLabourIntelligence: () => {}, updateForgottenItemWarnings: () => {},
  updateSupplierPreferenceNotes: () => {}, showNotice: () => {},
});
vm.runInContext(app.slice(app.indexOf('function applyAIQuoteDraft()'),
  app.indexOf('function discardAIQuoteDraft()')), context);
context.applyAIQuoteDraft();
assert.equal(applied[0].name, rows[0].name);
assert.equal(applied[0].manual_price, 42.5);
assert.equal(applied[0].supplier, 'City Plumbing');

const noMatch = {materials:[]};
context.CURRENT_SITE_SURVEY.material_actions[0].material_name = 'macerator pump';
context.reconcileRequiredSurveyMaterials(noMatch);
assert.equal(noMatch.materials.length, 1);
assert.equal(noMatch.materials[0].name, 'macerator pump');
assert.equal(noMatch.materials[0].manual_price, 0);
assert.equal(noMatch.materials[0].material_review.status, 'unmatched');

context.LAST_AI_QUOTE_DRAFT = noMatch;
context.searchDraftMaterialChoices(0, 'Fluidmaster');
assert.equal(noMatch.materials[0].material_review.choices[0].name, rows[1].name);
context.chooseDraftMaterial(0, 0);
assert.equal(noMatch.materials[0].name, rows[1].name);

console.log('Material selection regression: PASS');
