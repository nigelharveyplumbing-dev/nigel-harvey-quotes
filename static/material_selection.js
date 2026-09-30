// Conservative product selection for required materials identified at a site visit.
// Only saved Materials Database rows are eligible for an automatic product/price.
const MaterialSelection = (() => {
  const words = value => String(value || '').toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/).filter(Boolean)
    .map(word => word.endsWith('s') && word.length > 4 ? word.slice(0, -1) : word);
  const normal = value => words(value).join(' ');
  const price = row => Number(row.last_live_price || row.last_price ||
    row.last_manual_price || row.default_price || 0) || 0;
  const inchSize = value => {
    const match = String(value || '').toLowerCase()
      .match(/\b(\d+(?:\.\d+)?|\d+\s+\d+\/\d+)\s*(?:inch(?:es)?|["”])/);
    if (!match) return '';
    const parts = match[1].split(/\s+/);
    return parts.length === 2 ? Number(parts[0]) + Number(parts[1].split('/')[0]) /
      Number(parts[1].split('/')[1]) : Number(parts[0]);
  };

  function savedRows(rows) {
    const seen = new Set();
    return (rows || []).filter(row => {
      if (!row || !row.name) return false;
      const key = [normal(row.name), normal(row.supplier), String(row.url || '').toLowerCase()].join('|');
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function candidates(requested, rows) {
    const requestedWords = [...new Set(words(requested))];
    if (!requestedWords.length) return [];
    return savedRows(rows).map(row => {
      const productWords = [...new Set(words(row.name))];
      if (inchSize(requested) && inchSize(row.name) && inchSize(requested) !== inchSize(row.name)) return null;
      const accessoryWords = ['button', 'washer', 'seal', 'handle', 'diaphragm', 'kit'];
      if (accessoryWords.some(word => productWords.includes(word) && !requestedWords.includes(word))) return null;
      const sameSize = requestedWords.filter(word => /^\d+(?:mm|cm|l)$/.test(word));
      const productSizes = productWords.filter(word => /^\d+(?:mm|cm|l)$/.test(word));
      if (sameSize.length && productSizes.length &&
          sameSize.join('|') !== productSizes.join('|')) return null;
      if (!requestedWords.every(word => productWords.includes(word))) return null;
      return {
        name: row.name, supplier: row.supplier || '', url: row.url || '',
        price: price(row), price_status: row.last_status || '',
        exact: normal(requested) === normal(row.name),
        closeness: requestedWords.length / productWords.length
      };
    }).filter(Boolean).sort((a, b) => b.closeness - a.closeness ||
      a.name.localeCompare(b.name) || a.supplier.localeCompare(b.supplier)).slice(0, 10);
  }

  function review(requested, transcript, rows) {
    const choices = candidates(requested, rows);
    const spoken = ` ${normal(transcript)} `;
    const requestedWords = words(requested);
    // A product/model is explicit only when its complete saved name, including
    // distinguishing words beyond the generic requirement, occurs in the audio.
    const spokenProducts = choices.filter(choice => {
      const productWords = words(choice.name);
      return productWords.length > requestedWords.length && productWords.length >= 4 &&
        spoken.includes(` ${productWords.join(' ')} `);
    });
    spokenProducts.sort((a, b) => words(b.name).length - words(a.name).length);
    const explicit = spokenProducts[0] &&
      (!spokenProducts[1] || words(spokenProducts[0].name).length > words(spokenProducts[1].name).length)
      ? spokenProducts[0] : null;
    const uniqueNearExact = choices.length === 1 && choices[0].closeness >= 0.8;
    const specificExact = choices.filter(choice => choice.exact && words(choice.name).length >= 4);
    const selected = explicit || (specificExact.length === 1 ? specificExact[0] : null) ||
      (uniqueNearExact ? choices[0] : null);
    return {requested_name: requested, status: selected ? 'selected' : choices.length ? 'choose' : 'unmatched',
      selected: selected || null, choices};
  }

  return {review, candidates, savedRows};
})();
if (typeof module !== 'undefined') module.exports = MaterialSelection;
