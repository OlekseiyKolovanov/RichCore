const SERVICE_HEADERS = ['RC_Status', 'RC_Action', 'RC_GitHub_Item_ID', 'RC_Updated_At', 'RC_Note'];
const DONE_STATUSES = ['appointed', 'rejected', 'removed'];

const COLORS = {
  appointed: '#b6d7a8',
  rejected: '#d9d9d9',
  removed: '#ea9999',
  error: '#fff2cc',
};

function doGet(e) {
  return handleRequest_(e);
}

function doPost(e) {
  return handleRequest_(e);
}

function handleRequest_(e) {
  try {
    const request = parseRequest_(e);

    if (request.action === 'pending') {
      return json_({ ok: true, items: collectPending_() });
    }

    if (request.action === 'mark') {
      markRow_(request);
      return json_({ ok: true });
    }

    if (request.action === 'ping' || !request.action) {
      return json_({ ok: true, message: 'RichCore Apps Script is ready' });
    }

    throw new Error('Unknown action: ' + request.action);
  } catch (error) {
    return json_({ ok: false, error: String(error && error.message ? error.message : error) });
  }
}

function parseRequest_(e) {
  if (e && e.postData && e.postData.contents) {
    return JSON.parse(e.postData.contents);
  }
  return (e && e.parameter) || {};
}

function collectPending_() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    throw new Error('Open this script from the Google Sheet, not as a standalone script.');
  }

  const items = [];
  for (const sheet of spreadsheet.getSheets()) {
    const source = detectSource_(sheet);
    if (!source) {
      continue;
    }

    const columns = ensureServiceColumns_(sheet);
    const lastRow = sheet.getLastRow();
    const lastColumn = sheet.getLastColumn();
    if (lastRow < 2 || lastColumn < 1) {
      continue;
    }

    const range = sheet.getRange(1, 1, lastRow, lastColumn);
    const values = range.getDisplayValues();
    const backgrounds = range.getBackgrounds();
    const headers = values[0];

    for (let rowIndex = 1; rowIndex < values.length; rowIndex += 1) {
      const row = values[rowIndex];
      if (isEmptyRow_(row)) {
        continue;
      }

      const rowNumber = rowIndex + 1;
      const status = String(row[columns.RC_Status - 1] || '').trim().toLowerCase();
      if (DONE_STATUSES.indexOf(status) !== -1) {
        continue;
      }

      const rowColors = backgrounds[rowIndex];
      const isRed = isRedRow_(rowColors);
      const isGreen = isGreenRow_(rowColors);
      const isGray = isGrayRow_(rowColors);
      if (isGreen || isGray) {
        continue;
      }

      const record = normalizeRecord_(source, sheet, headers, row, rowNumber);
      record.action = isRed ? 'remove' : 'appoint';
      record.rowColor = firstVisibleColor_(rowColors);
      record.githubItemId = String(row[columns.RC_GitHub_Item_ID - 1] || '').trim();
      record.status = status;
      items.push(record);
    }
  }
  return items;
}

function markRow_(request) {
  const sheet = findSheet_(request);
  if (!sheet) {
    throw new Error('Sheet not found: ' + (request.sheetName || request.sheetId || request.sourceKey || 'unknown'));
  }
  const rowNumber = Number(request.rowNumber);
  if (!rowNumber || rowNumber < 2 || rowNumber > sheet.getLastRow()) {
    throw new Error('Bad row number: ' + request.rowNumber);
  }

  const columns = ensureServiceColumns_(sheet);
  const status = String(request.status || '').trim().toLowerCase();
  const action = status === 'removed' ? 'remove' : status === 'rejected' ? 'reject' : 'appoint';
  const color = COLORS[status] || COLORS.error;
  const now = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');

  sheet.getRange(rowNumber, columns.RC_Status).setValue(status);
  sheet.getRange(rowNumber, columns.RC_Action).setValue(action);
  sheet.getRange(rowNumber, columns.RC_GitHub_Item_ID).setValue(String(request.githubItemId || ''));
  sheet.getRange(rowNumber, columns.RC_Updated_At).setValue(now);
  sheet.getRange(rowNumber, columns.RC_Note).setValue(String(request.note || ''));
  sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).setBackground(color);
}

function detectSource_(sheet) {
  if (sheet.getLastRow() < 1 || sheet.getLastColumn() < 1) {
    return null;
  }
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
  const hasNickname = hasHeader_(headers, ['NickName', 'Nickname', 'Нікнейм']);
  const hasId = hasHeader_(headers, ['ID', 'Айді']);
  if (!hasNickname || !hasId) {
    return null;
  }

  const isLeadership = hasHeader_(headers, ['Посада']);
  return {
    key: String(sheet.getSheetId()),
    label: isLeadership ? 'Лідери / заступники' : 'Слідкуючі',
    type: isLeadership ? 'leadership' : 'watchers',
  };
}

function findSheet_(request) {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    return null;
  }
  const sheetId = String(request.sourceKey || request.sheetId || '').trim();
  const sheetName = String(request.sheetName || '').trim();
  for (const sheet of spreadsheet.getSheets()) {
    if (String(sheet.getSheetId()) === sheetId || sheet.getName() === sheetName) {
      return sheet;
    }
  }
  return null;
}

function ensureServiceColumns_(sheet) {
  let headers = sheet.getRange(1, 1, 1, Math.max(1, sheet.getLastColumn())).getDisplayValues()[0];
  for (const serviceHeader of SERVICE_HEADERS) {
    if (headers.indexOf(serviceHeader) === -1) {
      sheet.getRange(1, sheet.getLastColumn() + 1).setValue(serviceHeader);
      headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
    }
  }

  const result = {};
  headers.forEach((header, index) => {
    if (SERVICE_HEADERS.indexOf(header) !== -1) {
      result[header] = index + 1;
      try {
        sheet.hideColumns(index + 1);
      } catch (error) {
        // The column may already be hidden.
      }
    }
  });
  return result;
}

function normalizeRecord_(source, sheet, headers, row, rowNumber) {
  const position = valueByHeaders_(headers, row, ['Посада', 'Посада:', 'Position']);
  const role = source.type === 'watchers' ? 'watcher' : roleFromPosition_(position);
  const roleLabel = role === 'leader' ? 'Лідер' : role === 'deputy' ? 'Заступник' : 'Слідкуючий';
  const faction = source.type === 'watchers'
    ? valueByHeaders_(headers, row, ['Організація', 'Організація:', 'Фракція', 'Фракція:'])
    : valueByHeaders_(headers, row, ['Фракція', 'Фракція:', 'Організація', 'Організація:']);

  const email = valueByHeaders_(headers, row, [
    'Електронна пошта',
    'Електронна пошта:',
    'Email',
    'E-mail',
  ]);

  return {
    uid: source.key + ':' + rowNumber,
    sourceKey: source.key,
    sourceLabel: source.label,
    sheetId: source.key,
    sheetName: sheet.getName(),
    rowNumber,
    action: 'appoint',
    role,
    roleLabel,
    nickname: valueByHeaders_(headers, row, ['NickName', 'NickName:', 'Nickname', 'Нікнейм']),
    playerId: valueByHeaders_(headers, row, ['ID', 'ID:', 'Айді']),
    position,
    faction,
    appointDate: valueByHeaders_(headers, row, [
      'Дата призначення',
      'Дата призначення:',
      'Дата призначення / погодження',
      'Дата призначення / погодження:',
    ]),
    telegram: valueByHeaders_(headers, row, [
      'Telegram',
      'Telegram:',
      'Telegram для зв\'язку',
      'Telegram для зв\'язку:',
    ]),
    discord: valueByHeaders_(headers, row, ['Discord', 'Discord:']),
    forumUrl: valueByHeaders_(headers, row, [
      'Посилання на форумний акаунт',
      'Посилання на форумний акаунт:',
    ]),
    email,
    twoFaUrl: valueByHeaders_(headers, row, [
      '2FA',
      '2FA:',
      '2FA (скрін)',
      '2FA (скрін):',
      '2FA (двохфакторний захист акаунта)',
      '2FA (двохфакторний захист акаунта):',
    ]),
  };
}

function roleFromPosition_(position) {
  const text = String(position || '').toLowerCase();
  if (text.indexOf('заст') !== -1 || text.indexOf('зам') !== -1) {
    return 'deputy';
  }
  if (text.indexOf('лід') !== -1 || text.indexOf('лид') !== -1) {
    return 'leader';
  }
  return 'watcher';
}

function hasHeader_(headers, candidates) {
  const keys = headers.map(headerKey_);
  return candidates.some(candidate => keys.indexOf(headerKey_(candidate)) !== -1);
}

function valueByHeaders_(headers, row, candidates) {
  const keys = headers.map(headerKey_);
  for (const candidate of candidates) {
    const key = headerKey_(candidate);
    const exactIndex = keys.indexOf(key);
    if (exactIndex !== -1) {
      return String(row[exactIndex] || '').trim();
    }
  }
  for (const candidate of candidates) {
    const key = headerKey_(candidate);
    for (let index = 0; index < keys.length; index += 1) {
      if (keys[index] && key && (keys[index].indexOf(key) !== -1 || key.indexOf(keys[index]) !== -1)) {
        return String(row[index] || '').trim();
      }
    }
  }
  return '';
}

function headerKey_(value) {
  return String(value || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
}

function isEmptyRow_(row) {
  return row.every(value => String(value || '').trim() === '');
}

function firstVisibleColor_(colors) {
  for (const color of colors) {
    if (color && color !== '#ffffff') {
      return color;
    }
  }
  return '#ffffff';
}

function isRedRow_(colors) {
  return colors.some(color => ['#ff0000', '#cc0000', '#e06666', '#ea9999', '#f4cccc'].indexOf(String(color).toLowerCase()) !== -1);
}

function isGreenRow_(colors) {
  return colors.some(color => ['#00ff00', '#6aa84f', '#93c47d', '#b6d7a8', '#d9ead3'].indexOf(String(color).toLowerCase()) !== -1);
}

function isGrayRow_(colors) {
  return colors.some(color => ['#999999', '#b7b7b7', '#cccccc', '#d9d9d9', '#efefef'].indexOf(String(color).toLowerCase()) !== -1);
}

function json_(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
