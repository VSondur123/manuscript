-- Generic article-based doctypes print `author` as plain text. Flatten map authors
-- (author: [{name:, affiliation:, email:}]) to "Name (Affiliation)" strings. Plain-string authors are untouched.
-- Added by md_to_latex.py only when the front matter actually contains a map author.
local utils = pandoc.utils

function Meta(meta)
  if meta.author == nil then return nil end
  local list = utils.type(meta.author) == 'List' and meta.author or { meta.author }
  local changed, out = false, {}
  for _, a in ipairs(list) do
    if utils.type(a) == 'table' then
      changed = true
      local inl = pandoc.Inlines({})
      inl:extend(a.name or pandoc.Inlines({}))
      if a.affiliation ~= nil then
        local affs = {}
        local affl = utils.type(a.affiliation) == 'List' and a.affiliation or { a.affiliation }
        for _, af in ipairs(affl) do affs[#affs + 1] = utils.stringify(af) end
        if #affs > 0 then
          inl:extend(pandoc.Inlines({ pandoc.Space(), pandoc.Str('(' .. table.concat(affs, '; ') .. ')') }))
        end
      end
      out[#out + 1] = pandoc.MetaInlines(inl)
    else
      out[#out + 1] = a
    end
  end
  if changed then meta.author = pandoc.MetaList(out); return meta end
  return nil
end
