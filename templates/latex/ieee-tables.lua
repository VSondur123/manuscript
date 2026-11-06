-- Render pandoc tables as single-column IEEE-compatible tabular floats (longtable breaks in two-column mode).
-- Add the attribute {.wide} is not supported on tables by pandoc; wide tables should be split or kept narrow.
local function cell_tex(cell)
  local s = pandoc.write(pandoc.Pandoc(cell.contents), 'latex')
  s = s:gsub('^%s+', ''):gsub('%s+$', ''):gsub('\n\n+', ' '):gsub('\n', ' ')
  return s
end

function Table(tbl)
  local ncol = #tbl.colspecs
  local spec = {}
  for i, cs in ipairs(tbl.colspecs) do
    local w = cs[2]
    if type(w) == 'number' and w > 0 then
      spec[#spec + 1] = string.format('p{%.3f\\columnwidth}', math.max(w * 0.96 - 0.02, 0.08))
    else
      spec[#spec + 1] = 'l'
    end
  end
  local lines = {}
  local label = tbl.identifier ~= '' and ('\\label{' .. tbl.identifier .. '}') or ''
  local cap = ''
  if tbl.caption and tbl.caption.long and #tbl.caption.long > 0 then
    cap = pandoc.write(pandoc.Pandoc(tbl.caption.long), 'latex'):gsub('\n+$', '')
  end
  lines[#lines + 1] = '\\begin{table}[htbp]'
  lines[#lines + 1] = '\\caption{' .. cap .. '}' .. label
  lines[#lines + 1] = '\\centering\\footnotesize'
  lines[#lines + 1] = '\\begin{tabular}{' .. table.concat(spec, ' ') .. '}'
  lines[#lines + 1] = '\\hline'
  local function row_tex(row, bold)
    local cells = {}
    for _, c in ipairs(row.cells) do
      local t = cell_tex(c)
      if bold and t ~= '' then t = '\\textbf{' .. t .. '}' end
      cells[#cells + 1] = t
    end
    return table.concat(cells, ' & ') .. ' \\\\'
  end
  for _, r in ipairs(tbl.head.rows) do lines[#lines + 1] = row_tex(r, true) end
  if #tbl.head.rows > 0 then lines[#lines + 1] = '\\hline' end
  for _, body in ipairs(tbl.bodies) do
    for _, r in ipairs(body.body) do lines[#lines + 1] = row_tex(r, false) end
  end
  lines[#lines + 1] = '\\hline'
  lines[#lines + 1] = '\\end{tabular}'
  lines[#lines + 1] = '\\end{table}'
  return pandoc.RawBlock('latex', table.concat(lines, '\n'))
end
