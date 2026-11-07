-- Shared by the venue templates (llncs, elsevier, preprint).
-- Normalises the `author` metadata (plain string, list of strings, or list of maps with name/affiliation/email/...)
-- and derives numbered, de-duplicated affiliations so templates need no index arithmetic:
--   author[i].name      Inlines
--   author[i].affids    "1,2"   comma-joined affiliation numbers (absent when the author has no affiliation)
--   affiliations[k]     {id="k", text=<Inlines>, emails="a@x, b@y"}   emails of the authors in that affiliation
--   authorrunning       "A. Smith and B. Doe" / "A. Smith et al."  (unless set in the front matter)
local utils = pandoc.utils

local function as_list(v)
  if v == nil then return {} end
  local t = utils.type(v)
  if t == 'List' then return v end
  return { v }
end

function Meta(meta)
  local authors, affs, index = {}, {}, {}
  for _, a in ipairs(as_list(meta.author)) do
    local t = utils.type(a)
    local entry
    if t == 'table' then
      entry = {}
      for k, v in pairs(a) do entry[k] = v end
    else
      entry = { name = a }
    end
    local ids = {}
    for _, aff in ipairs(as_list(entry.affiliation)) do
      local key = utils.stringify(aff)
      if key ~= '' then
        if not index[key] then
          affs[#affs + 1] = { id = tostring(#affs + 1), text = aff, emails = {} }
          index[key] = #affs
        end
        ids[#ids + 1] = tostring(index[key])
        if entry.email then
          local list = affs[index[key]].emails
          list[#list + 1] = utils.stringify(entry.email)
        end
      end
    end
    if #ids > 0 then entry.affids = table.concat(ids, ',') end
    authors[#authors + 1] = entry
  end
  if #authors == 0 then return nil end
  for _, af in ipairs(affs) do af.emails = table.concat(af.emails, ', ') end
  meta.author = authors
  if #affs > 0 then meta.affiliations = affs end
  if not meta.authorrunning then
    local names = {}
    for _, a in ipairs(authors) do names[#names + 1] = utils.stringify(a.name) end
    if #names == 1 then meta.authorrunning = names[1]
    elseif #names == 2 then meta.authorrunning = names[1] .. ' and ' .. names[2]
    else meta.authorrunning = names[1] .. ' et al.' end
  end
  return meta
end
