/**
 * tag-validator.js
 * Validates and enforces tag rules across all automation workflows
 */

const ALLOWED_TAGS = [
  'potential client',
  'high potential',
  'active client',
  'past client',
  'cold',
  'warm',
  'do not contact'
];

const BLOCKED_TAGS = ['do not contact'];

/**
 * Check if a tag is valid
 */
function isValidTag(tag) {
  return ALLOWED_TAGS.includes(tag?.toLowerCase()?.trim());
}

/**
 * Check if a contact should receive messages
 */
function isContactable(contact) {
  const tag = contact.Tag?.toLowerCase()?.trim();
  const optOut = contact['WhatsApp Opt-Out'];
  
  if (optOut === true || optOut === 'TRUE' || optOut === true) return false;
  if (BLOCKED_TAGS.includes(tag)) return false;
  if (!tag) return false;
  
  return true;
}

/**
 * Filter contacts for broadcast by tag
 * @param {Array} contacts - All contacts from Sheet
 * @param {string} targetTag - Tag from Telegram command
 * @returns {Array} - Filtered, contactable list
 */
function filterByTag(contacts, targetTag) {
  const normalizedTarget = targetTag?.toLowerCase()?.trim();
  
  if (!isValidTag(normalizedTarget)) {
    throw new Error(`Invalid tag: "${targetTag}". Allowed: ${ALLOWED_TAGS.join(', ')}`);
  }

  return contacts.filter(contact => {
    const contactTag = contact.Tag?.toLowerCase()?.trim();
    return contactTag === normalizedTarget && isContactable(contact);
  });
}

module.exports = { isValidTag, isContactable, filterByTag, ALLOWED_TAGS };

// ─── n8n Code Node Usage ───────────────────────────────────────────────────
// Filter contacts by tag in n8n Code node:
//
// const items = $input.all();
// const targetTag = $('Telegram Trigger').first().json.message.text
//   .split(' ')[1]?.toLowerCase()?.trim();
//
// const BLOCKED = ['do not contact'];
// const filtered = items.filter(item => {
//   const tag = item.json.Tag?.toLowerCase()?.trim();
//   const optOut = item.json['WhatsApp Opt-Out'];
//   return tag === targetTag && !BLOCKED.includes(tag) && optOut !== 'TRUE';
// });
//
// if (filtered.length === 0) {
//   throw new Error(`No contacts found for tag: ${targetTag}`);
// }
//
// return filtered;
