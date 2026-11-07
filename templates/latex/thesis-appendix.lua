-- Appendices: everything from the first level-1 heading marked {.appendix} to the end of the document is moved into the
-- metadata variable `appendix-body`, which thesis.latex prints AFTER the bibliography behind \appendix, so the chapters are
-- lettered ("Appendix A", "Appendix B", ...) and the references stay before them. Content is never altered.
-- An empty References/Bibliography heading right before the first appendix is dropped when BibTeX prints the bibliography;
-- with a CSL style the generated bibliography is kept under that heading, before the appendices.
local function is_refs_heading(b)
  if b.t ~= "Header" or b.level ~= 1 then return false end
  local t = pandoc.utils.stringify(b.content):lower()
  return t == "references" or t == "bibliography"
end

function Pandoc(doc)
  local first
  for i, b in ipairs(doc.blocks) do
    if b.t == "Header" and b.level == 1 and b.classes:includes("appendix") then first = i; break end
  end
  if not first then return nil end
  local body, appendix = {}, {}
  for i, b in ipairs(doc.blocks) do
    if i < first then body[#body + 1] = b else appendix[#appendix + 1] = b end
  end
  -- citeproc (CSL styles) appends the bibliography div at the very end of the document: bring it back before the appendices
  local rest, refs = {}, nil
  for _, b in ipairs(appendix) do
    if b.t == "Div" and b.identifier == "refs" then refs = b else rest[#rest + 1] = b end
  end
  appendix = rest
  if refs then
    body[#body + 1] = refs
  elseif #body > 0 and is_refs_heading(body[#body]) then
    table.remove(body)
  end
  doc.blocks = body
  doc.meta["appendix-body"] = pandoc.MetaBlocks(appendix)
  return doc
end
