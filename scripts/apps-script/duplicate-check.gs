/**
 * Duplicate pre-check for the Masdar intake form.
 *
 * Runs in the register spreadsheet on every form submission. Normalises the submitted
 * source URL, compares it against every row already in the sheet, and — on a hit —
 * flags the row and emails the contributor.
 *
 * This catches dedup layer 1 (the same online source submitted twice), which is by far
 * the most common case, before anyone spends work on it. Layers 2–5 need the backend.
 *
 * Setup: Extensions > Apps Script, paste this file, then
 *   Triggers > Add trigger > onFormSubmit > From spreadsheet > On form submit
 */

// Column headers, exactly as they appear in row 1. Adjust if you rename them.
var COL_SOURCE_URL = 'Link to where you found it';
var COL_SCHOLAR = 'Which scholar?';
var COL_EMAIL = 'Email Address';
var COL_NAME = 'Your name';
var COL_FLAG = 'possible_duplicate_of';
var COL_ID = 'id';

var NOTIFY_CONTRIBUTOR = true;

function onFormSubmit(e) {
  var sheet = e.range.getSheet();
  var row = e.range.getRow();
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];

  var urlCol = headers.indexOf(COL_SOURCE_URL) + 1;
  var flagCol = headers.indexOf(COL_FLAG) + 1;
  if (urlCol === 0 || flagCol === 0) {
    console.error('Missing column. Need "' + COL_SOURCE_URL + '" and "' + COL_FLAG + '".');
    return;
  }

  var submitted = normaliseSource(sheet.getRange(row, urlCol).getValue());
  if (!submitted.key) return;  // no usable URL — nothing to compare against

  var match = findEarlierMatch(sheet, headers, row, submitted.key, urlCol);
  if (!match) return;

  var label = match.id || ('row ' + match.row);
  sheet.getRange(row, flagCol).setValue(label);
  sheet.getRange(row, flagCol).setNote(
    'Same source as ' + label + '. Checked automatically on submission.');

  if (NOTIFY_CONTRIBUTOR) notifyContributor(sheet, headers, row, label);
}

/**
 * Reduce a URL to a comparison key. Two links to the same recording must produce the
 * same key even when one carries tracking parameters, a timestamp, or a different host
 * spelling — that is the whole point.
 */
function normaliseSource(raw) {
  if (!raw) return { key: null, platformId: null };
  var url = String(raw).trim();
  if (!url) return { key: null, platformId: null };

  var videoId = youTubeId(url);
  if (videoId) return { key: 'youtube:' + videoId, platformId: 'youtube:' + videoId };

  // Not a known platform: strip the noise and compare what remains.
  var cleaned = url
    .replace(/^https?:\/\//i, '')
    .replace(/^www\./i, '')
    .replace(/#.*$/, '')
    .replace(/[?&](utm_[^=]+|fbclid|gclid|si|feature|app)=[^&]*/gi, '')
    .replace(/[?&]$/, '')
    .replace(/\/+$/, '')
    .toLowerCase();
  return { key: cleaned || null, platformId: null };
}

function youTubeId(url) {
  var patterns = [
    /(?:youtube\.com|youtube-nocookie\.com)\/watch\?(?:.*&)?v=([A-Za-z0-9_-]{11})/i,
    /youtu\.be\/([A-Za-z0-9_-]{11})/i,
    /(?:youtube\.com|youtube-nocookie\.com)\/(?:embed|shorts|live|v)\/([A-Za-z0-9_-]{11})/i
  ];
  for (var i = 0; i < patterns.length; i++) {
    var m = url.match(patterns[i]);
    if (m) return m[1];
  }
  return null;
}

/** First earlier row whose source resolves to the same key. */
function findEarlierMatch(sheet, headers, currentRow, key, urlCol) {
  var last = sheet.getLastRow();
  if (last < 3) return null;

  var urls = sheet.getRange(2, urlCol, last - 1, 1).getValues();
  var idCol = headers.indexOf(COL_ID) + 1;
  var ids = idCol > 0 ? sheet.getRange(2, idCol, last - 1, 1).getValues() : null;

  for (var i = 0; i < urls.length; i++) {
    var rowNumber = i + 2;
    if (rowNumber >= currentRow) continue;
    if (normaliseSource(urls[i][0]).key === key) {
      return { row: rowNumber, id: ids ? String(ids[i][0] || '').trim() : '' };
    }
  }
  return null;
}

function notifyContributor(sheet, headers, row, label) {
  var emailCol = headers.indexOf(COL_EMAIL) + 1;
  if (emailCol === 0) return;
  var to = String(sheet.getRange(row, emailCol).getValue() || '').trim();
  if (!to) return;

  var nameCol = headers.indexOf(COL_NAME) + 1;
  var name = nameCol > 0 ? String(sheet.getRange(row, nameCol).getValue() || '').trim() : '';
  var greeting = name ? ('As-salāmu ʿalaykum ' + name + ',') : 'As-salāmu ʿalaykum,';

  var body = [
    greeting,
    '',
    'Jazākallāhu khayran for the submission.',
    '',
    'It looks like we already have this one — it matches entry ' + label + '.',
    '',
    'If yours is actually a different recording (a longer version, better audio, or the',
    'question included where the other one starts at the answer), just reply and say so.',
    'Those are worth keeping, and the admin will link them instead of dropping one.',
    '',
    'No action needed otherwise.',
    '',
    'Bārakallāhu fīk'
  ].join('\n');

  try {
    MailApp.sendEmail(to, 'Masdar — we may already have this recording', body);
  } catch (err) {
    console.error('Could not email ' + to + ': ' + err);
  }
}

/** Run once from the editor to check the URL matching against known cases. */
function testNormalisation() {
  var sameRecording = [
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://youtu.be/dQw4w9WgXcQ?si=abc123',
    'http://m.youtube.com/watch?v=dQw4w9WgXcQ&t=42s',
    'https://www.youtube.com/shorts/dQw4w9WgXcQ'
  ];
  var keys = sameRecording.map(function (u) { return normaliseSource(u).key; });
  var allSame = keys.every(function (k) { return k === keys[0]; });
  console.log(allSame ? 'PASS — all four resolve to ' + keys[0] : 'FAIL — ' + keys.join(' | '));

  var a = normaliseSource('https://binothaimeen.net/content/1234/').key;
  var b = normaliseSource('http://www.binothaimeen.net/content/1234?utm_source=tg#x').key;
  console.log(a === b ? 'PASS — non-platform URLs match' : 'FAIL — ' + a + ' vs ' + b);

  var c = normaliseSource('https://www.youtube.com/watch?v=dQw4w9WgXcQ').key;
  var d = normaliseSource('https://www.youtube.com/watch?v=XXXXXXXXXXX').key;
  console.log(c !== d ? 'PASS — different videos differ' : 'FAIL — collision');
}
