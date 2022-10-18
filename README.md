# VE Diagram Generator

Parses cross-reference directives in confluence wiki documents, renders their views, and upserts the wiki documents.


### Sample `.env` file:
```sh
#!/bin/bash
export USER=jdoe
export PASS='pA55w0rd123'

export CONFLUENCE_SERVER=https://confluence.domain.org
export CONFLUENCE_USER="$USER"
export CONFLUENCE_PASS="$PASS"

export INCQUERY_SERVER=https://incquery.domain.org
export INCQUERY_USER="$USER"
export INCQUERY_PASS="$PASS"

export SPARQL_ENDPOINT=https://triplestore.domain.org/sparql
```

### Example CLI usage

Run `python3 -m ve_diagram_generator --help` to see CLI options.

```console
$ python3 -m ve_diagram_generator --help
RDFLib Version: 5.0.0
usage: ve_diagram_generator [-h] [-c COMPARTMENT_URI] [-m MOPID] -p PAGE_ID -s SPACE [--incquery-server INCQUERY_SERVER]
                            [--confluence-server CONFLUENCE_SERVER] [--sparql-endpoint SPARQL_ENDPOINT]

render all views for the given set of pages

optional arguments:
  -h, --help            show this help message and exit
  -c COMPARTMENT_URI, --compartment-uri COMPARTMENT_URI
                        IncQuery Compartment URI
  -m MOPID, --mopid MOPID
                        MMS Org / Project ID (#ref)
  -p PAGE_ID, --page-id PAGE_ID
                        Page ID(s)
  -s SPACE, --space SPACE
                        Confluence Wiki space ID
  --incquery-server INCQUERY_SERVER
  --confluence-server CONFLUENCE_SERVER
  --sparql-endpoint SPARQL_ENDPOINT

```
