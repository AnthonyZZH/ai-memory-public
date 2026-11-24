export {createMainLibraryAdapter, LibraryError, LIBRARY_TOOL_NAMES} from './core.mjs';
import {registerLibraryTools} from './core.mjs';

const text = (description, required = true) => ({ type: 'string', description, required });
const fields = {
  health: {},
  search: { query: text('Search the owner main library'), page: { type: 'number' }, page_size: { type: 'number' } },
  read: { identifier: text('Relative identifier from main search; no URLs'), include_content: { type: 'boolean' } },
  write: { title: text('New note title'), content: text('Owner-requested note content'), directory: text('Relative folder; . for root') },
  edit: { identifier: text('Exact existing relative identifier'), operation: text('append, prepend, or find_replace'), content: text('New content'), find_text: text('Exact single replacement target', false), expected_checksum: text('Checksum from a fresh read') },
};

export function registerOwnerLibraryTools(options) {
  return registerLibraryTools(options, {fields, describe: operation => `Owner private main library ${operation}.`});
}
