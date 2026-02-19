/**
 * phone-formatter.js
 * Normalizes phone numbers to E.164 format for WhatsApp Cloud API
 * 
 * WhatsApp requires: no + prefix, just digits
 * E.g. "+2348012345678" → "2348012345678"
 */

/**
 * Strips non-numeric characters and removes leading +
 * @param {string} phone - Raw phone number from Google Sheets
 * @returns {string} - Cleaned phone for WhatsApp API
 */
function formatForWhatsApp(phone) {
  if (!phone || typeof phone !== 'string') return null;

  // Remove all non-digit characters (spaces, dashes, parens, +)
  let cleaned = phone.replace(/\D/g, '');

  // Remove leading zeros (common in local Nigerian format: 08012345678 → 8012345678)
  // Then prepend country code if missing
  // Nigerian numbers: should start with 234
  if (cleaned.startsWith('0') && cleaned.length === 11) {
    // Local format: 08012345678 → 2348012345678
    cleaned = '234' + cleaned.substring(1);
  }

  // Validate: must be 7–15 digits (ITU E.164 standard)
  if (cleaned.length < 7 || cleaned.length > 15) {
    return null; // Invalid — will be logged to Errors tab
  }

  return cleaned;
}

/**
 * Validates that a number is ready for WhatsApp
 * @param {string} phone 
 * @returns {boolean}
 */
function isValidWhatsAppNumber(phone) {
  const formatted = formatForWhatsApp(phone);
  return formatted !== null;
}

/**
 * Batch format an array of contact objects from Google Sheets
 * @param {Array} contacts - Array of row objects from n8n Google Sheets node
 * @returns {Array} - Contacts with formatted phone + invalid flagged
 */
function batchFormat(contacts) {
  return contacts.map(contact => {
    const formatted = formatForWhatsApp(contact.Phone);
    return {
      ...contact,
      phone_formatted: formatted,
      phone_valid: formatted !== null
    };
  }).filter(c => {
    if (!c.phone_valid) {
      console.error(`Invalid phone skipped: ${c.Phone} for contact: ${c.Name}`);
    }
    return c.phone_valid;
  });
}

module.exports = { formatForWhatsApp, isValidWhatsAppNumber, batchFormat };

// ─── n8n Code Node Usage ───────────────────────────────────────────────────
// In n8n "Code" node, paste this logic directly:
//
// const items = $input.all();
// const result = [];
// for (const item of items) {
//   let phone = item.json.Phone || '';
//   phone = phone.replace(/\D/g, '');
//   if (phone.startsWith('0') && phone.length === 11) {
//     phone = '234' + phone.substring(1);
//   }
//   if (phone.length >= 7 && phone.length <= 15) {
//     result.push({ json: { ...item.json, phone_formatted: phone } });
//   }
// }
// return result;
