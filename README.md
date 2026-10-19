# arXiv Search and Source Downloader

NanoAgent's built-in reference plugin: the `nanoagent.plugin/v0001` contract,
and the structure `nanoagent plugin new` gives every new plugin. The
plugin is a standard MCP server over stdio; NanoAgent owns its launch command,
environment, input and output checks and lifecycle.

## Tools

| Tool | Does | Code |
|---|---|---|
| `search_papers` | Finds papers on arXiv and their arXiv ids: the one paper an arXiv id or URL in the query names, else the best matches for its words, each with its title, authors, abstract and date, from the first search engine to find any | `src/plugin/search.py` |
| `download_source` | Saves one paper's source in `<destination>/<arxiv id>/`: what is there already, else its archive (`export.arxiv.org/src/<id>`) downloaded and unpacked safely | `src/plugin/download.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `search-papers` | Searches arXiv for papers | `tool`, with `search_papers` |
| `save-paper-source` | Saves a paper's LaTeX source by its arXiv ID | `tool`, with `download_source` |
| `find-and-save-paper` | Finds a described paper and saves its LaTeX source | `agent`, with `search_papers` and `download_source` |

The plugin does one thing: it finds a paper's arXiv id, then saves its source.
A query is an arXiv id or URL, or plain words such as `attention is all you
need vaswani`. It goes to OpenAlex (`api.openalex.org`) first, so arXiv is
asked as little as it can be, which keeps under its rate limit; then to
arXiv's own search (`export.arxiv.org/api/query`); then to DataCite
(`api.datacite.org`), which registers every arXiv paper's DOI. Each has 1 s to
answer: one that fails, is slower or finds nothing is passed over for the
next, and the result names the engine that answered and why each before it
did not. A paper's source is saved in a folder named by its id, and asking for
it again uses that folder without asking arXiv. arXiv is asked again when it
is busy (503) and never when it limits this computer (429), which fails at once.

People use the plugin by chatting: the chat agent turns a request into one of
its tasks. `search-papers` and `save-paper-source` each run one tool, and their
output is that tool's. `find-and-save-paper` takes the paper as the person
describes it and gives an agent `search_papers` and `download_source`, so it
can pick the right result itself; it submits the paper with its saved folder
(not the files, which `download_source`'s own check already held to the
archive), and `verifier/find.py` checks that the paper is the one whose source
fills `<destination>/<arxiv id>`.

## Layout

It has the standard plugin layout, which NanoAgent requires:

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none here)
├── src/plugin/      # the MCP server (__main__.py, its IMPLEMENTATIONS table) and the tools
├── tests/
├── ui/              # how the page draws the outputs: renderers.js (papers as cards) and renderers.css
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier package, one module per tool, and find.py for find-and-save-paper
```

`contract.py` types every value: the server builds each call's input into its
class and checks its output against its own, and NanoAgent and the verifier
get the same classes. A failing tool raises, and the MCP server returns an
error result.

`verifier/` is deterministic: it imports only the standard library and
`contract`, and checks what the types cannot say about inputs (arXiv ids,
queries, result counts, destinations) and outputs. For
outputs it checks that the papers are well formed and unique and within
`max_results`, that every folder is `<destination>/<arxiv id>` inside the workspace,
and that its files are exactly the declared ones. A tool task's output is
judged as its tool's is.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
```

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`;
`destination` is a folder inside it, each paper's source in `<destination>/<arxiv id>`.
