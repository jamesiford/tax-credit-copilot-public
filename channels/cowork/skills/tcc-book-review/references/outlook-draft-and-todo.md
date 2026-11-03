# Outlook drafts and the To Do list

Create these only for the clients the user selected. **Drafts are saved, never sent.** Say so
each time you create one.

## Draft

- **To:** the person you found in the client's most recent thread, if one exists. If you found
  nobody, leave To empty and say so. Do not guess an address.
- **Subject:** `<Client> — a conversation about your tax credit position`
- **Body, in this order:**
  1. One sentence that picks up the last contact or open thread ("Following your question on ...").
     If none was found, a plain introduction instead.
  2. Two sentences on why you are writing, from the **reason** the book gave (for example that
     the client is close to a statutory threshold, or has identified credit not yet claimed).
     Use the words the tool used. If you quote a figure, copy the tool's line that holds it,
     character for character.
  3. One sentence proposing a short call. No dates or times unless the user gave them.
  4. The disclaimer from the tool results, as written.

Never state or imply a figure the tools did not return. Never promise a credit or an outcome.
Run each body through `verify_figures` before saving it.

## To Do

One task per selected client:

- **Title:** `Call <Client>: <reason>`
- **Notes:** the open thread in your words, the suggested opener, and a reminder that the
  figures are quoted from the Tax Credit Copilot run and not to be restated from memory.
- **Due:** only if the user gave a date.

## What not to do

- Do not send, schedule or forward anything.
- Do not copy payroll, employee or personal detail from a tool result into a draft. The call
  plan carries client-level figures only.
- Do not create tasks or drafts for clients the user did not select.
