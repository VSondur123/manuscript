-- ManuScript DOCX filter (stand-in for pandoc-crossref, which is not required).
-- 1. numbers captioned figures and tables in document order and prefixes their captions ("Figure 1. ...")
-- 2. numbers headings (when metadata ms-number-sections is true) so "Section" links can name their number
-- 3. rewrites "[Figure](#fig-x)" style links to "Figure 1" (kept as an internal Word hyperlink)
-- 4. optional thesis cover lines from metadata (institution, faculty, department, degree, supervisor)
-- Unresolvable links are left as written and reported on stderr as "MS-UNRESOLVED-REF <id>".
local stringify = pandoc.utils.stringify
local NBSP = "\u{a0}"
local words = { Figure = "fig", ["Fig."] = "fig", Table = "tbl", ["Tab."] = "tbl", Section = "sec", ["Sec."] = "sec",
                Chapter = "sec", Appendix = "sec" }
local numbers = {}          -- identifier -> {kind=, n=}
local fig_n, tbl_n = 0, 0
local counters = {0, 0, 0, 0, 0, 0}
local number_sections = false

local function prefix_caption(caption, label)
  local long = caption.long
  if #long == 0 then return false end
  local first = long[1]
  if first.t == "Plain" or first.t == "Para" then
    first.content:insert(1, pandoc.Str(label .. ". "))
    return true
  end
  return false
end

local function has_class(el, c)
  for _, k in ipairs(el.classes) do if k == c then return true end end
  return false
end

local numbering_pass = {
  Figure = function(el)
    if #el.caption.long == 0 then return nil end
    fig_n = fig_n + 1
    if el.identifier ~= "" then numbers[el.identifier] = { kind = "fig", n = tostring(fig_n) } end
    prefix_caption(el.caption, "Figure " .. fig_n)
    return el
  end,
  Table = function(el)
    if #el.caption.long == 0 then return nil end
    tbl_n = tbl_n + 1
    if el.identifier ~= "" then numbers[el.identifier] = { kind = "tbl", n = tostring(tbl_n) } end
    prefix_caption(el.caption, "Table " .. tbl_n)
    return el
  end,
  Header = function(el)
    if not number_sections or has_class(el, "unnumbered") then return nil end
    local lvl = math.min(el.level, 6)
    counters[lvl] = counters[lvl] + 1
    for i = lvl + 1, 6 do counters[i] = 0 end
    local parts = {}
    for i = 1, lvl do parts[#parts + 1] = tostring(counters[i]) end
    if el.identifier ~= "" then numbers[el.identifier] = { kind = "sec", n = table.concat(parts, ".") } end
    return nil
  end,
}

local link_pass = {
  Link = function(el)
    local id = el.target:match("^#(.+)$")
    if not id then return nil end
    local text = stringify(el.content)
    local kind = words[text]
    if not kind then return nil end
    if kind == "sec" and not number_sections then return nil end  -- headings carry no visible number
    local ref = numbers[id]
    if not ref or ref.kind ~= kind then
      io.stderr:write("MS-UNRESOLVED-REF " .. id .. "\n")
      return nil
    end
    el.content = { pandoc.Str(text .. NBSP .. ref.n) }
    return el
  end,
}

local function cover(meta)
  local blocks = {}
  local function add(txt)
    if txt and txt ~= "" then
      blocks[#blocks + 1] = pandoc.Div({ pandoc.Para({ pandoc.Str(txt) }) }, pandoc.Attr("", {}, { { "custom-style", "Cover Line" } }))
    end
  end
  for _, k in ipairs({ "degree", "department", "faculty", "institution" }) do
    if meta[k] then add(stringify(meta[k])) end
  end
  if meta.supervisor then
    local names = {}
    if meta.supervisor.t == "MetaList" then
      for _, v in ipairs(meta.supervisor) do names[#names + 1] = stringify(v) end
    else
      names[1] = stringify(meta.supervisor)
    end
    add((#names > 1 and "Supervisors: " or "Supervisor: ") .. table.concat(names, ", "))
  end
  return blocks
end

return {
  { Meta = function(meta)
      local v = meta["ms-number-sections"]
      number_sections = v ~= nil and (v == true or stringify(v) == "true")
    end },
  numbering_pass,
  link_pass,
  { Pandoc = function(doc)
      local c = cover(doc.meta)
      if #c > 0 then
        local blocks = pandoc.List(c)
        blocks:extend(doc.blocks)
        return pandoc.Pandoc(blocks, doc.meta)
      end
    end },
}
