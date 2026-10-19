// How this plugin's page draws its tasks' outputs: papers as cards (title, authors, date, abstract
// and links), each search result with a button to save its source, and saved sources as their
// folder and files.
import { disclosure, h, icon, plural } from "./kit/components.js";

const DAY = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const SHOWN = 5;
const AUTHORS = 4;

/** "1706.03762v7" -> "1706.03762". */
const baseId = (id) => id.replace(/v\d+$/, "");
const external = (href, label) => h("a", { href, target: "_blank", rel: "noopener noreferrer", text: label });

function authorLine(authors) {
  if (authors.length <= AUTHORS) return authors.join(", ");
  return `${authors.slice(0, AUTHORS).join(", ")} and ${plural(authors.length - AUTHORS, "other")}`;
}

/** A line over the papers: an icon and what they are. */
const note = (name, text) => h("p", { class: "paper-note muted" }, icon(name, { size: 16 }), text);

/** "3 papers", or "No papers". */
const count = (items) => (items.length ? plural(items.length, "paper") : "No papers");

/** The first `SHOWN` items, the rest behind a disclosure. */
function capped(items, draw) {
  const list = h("ol", { class: "paper-list" }, items.slice(0, SHOWN).map(draw));
  if (items.length <= SHOWN) return list;
  return h(
    "div",
    { class: "papers" },
    list,
    disclosure(
      { summary: `Show ${items.length - SHOWN} more` },
      h("ol", { class: "paper-list" }, items.slice(SHOWN).map(draw)),
    ),
  );
}

/** A saved folder: its path and, behind a disclosure, its files. */
const savedFolder = (folder, files) =>
  disclosure(
    { summary: h("code", { text: folder }), hint: plural(files.length, "file"), className: "saved-folder" },
    h("ul", { class: "file-list" }, files.map((file) => h("li", {}, h("code", { text: file })))),
  );

/** One paper: its title (a link to arXiv), authors, date and id, then whatever `extra` adds. */
function paper({ title, url, authors, published, arxiv_id }, ...extra) {
  return h(
    "li",
    { class: "paper" },
    h("h4", { class: "paper-title" }, external(url, title)),
    h("p", { class: "paper-authors", text: authorLine(authors) }),
    h(
      "p",
      { class: "paper-meta muted" },
      published ? h("span", { text: DAY.format(new Date(published)) }) : null,
      h("code", { text: baseId(arxiv_id) }),
    ),
    extra,
  );
}

const abstract = (summary) =>
  summary ? disclosure({ summary: "Abstract", className: "paper-abstract" }, h("p", { text: summary })) : null;

function searchedPaper(found, send) {
  const id = baseId(found.arxiv_id);
  return paper(
    { ...found, url: found.abs_url },
    abstract(found.summary),
    h(
      "div",
      { class: "paper-actions" },
      h(
        "button",
        { type: "button", class: "button small", onclick: () => send(`Save the source of arXiv ${id}.`) },
        icon("folder", { size: 14 }),
        "Save source",
      ),
      external(found.abs_url.replace("/abs/", "/pdf/"), "PDF"),
    ),
  );
}

export default {
  SearchOutput: ({ query, engine, papers }, { send }) =>
    h(
      "div",
      { class: "papers" },
      note("search", `${count(papers)} for ${query}, from ${engine}`),
      papers.length ? capped(papers, (found) => searchedPaper(found, send)) : null,
    ),
  FoundPaperOutput: (found) =>
    h(
      "ol",
      { class: "paper-list" },
      paper(
        { ...found, url: found.abs_url },
        abstract(found.summary),
        h("p", { class: "paper-meta muted" }, icon("folder", { size: 14 }), h("code", { text: found.folder })),
      ),
    ),
  DownloadOutput: ({ arxiv_id, folder, files, reused }) =>
    h(
      "div",
      { class: "papers" },
      note("check", reused ? `The source of ${arxiv_id} was saved already` : `Saved the source of ${arxiv_id}`),
      savedFolder(folder, files),
    ),
};
