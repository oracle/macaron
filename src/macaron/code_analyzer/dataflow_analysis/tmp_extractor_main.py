import pprint
import sys
import os

from macaron.code_analyzer.dataflow_analysis.github_workflow_extractor import extract_from_workflow
from macaron.code_analyzer.dataflow_analysis import facts
from macaron.parsers.actionparser import parse

workflow_filepath = sys.argv[1]

workflow = parse(workflow_filepath)

node = extract_from_workflow(workflow)

db = facts.FactDatabase()

node.convert_to_facts(db)

db.top_level_block.add(facts.BlockId(node.id))

os.makedirs("facts_output")

db.write_to_files("facts_output")

pprint.pprint(node, width=200)
