"""Graph builder — multi-year extraction with tailored RAG."""

from langgraph.graph import StateGraph, START, END
from mlflow.models import set_model

from graph.graph_state import FinancialGraphState
from nodes.read_creditlens_template import read_creditlens_template
from nodes.annual_report_parser import annual_report_parser
from nodes.source_language import source_language
from nodes.select_pages import select_pages
from nodes.connect_llm import connect_llm
from nodes.build_rag_index import build_rag_index
from nodes.answer_questions import answer_questions
from nodes.confidence_refinement import confidence_refinement
from nodes.create_excel_output import create_excel_output

def build_graph():
    workflow = StateGraph(FinancialGraphState)

    workflow.add_node("read_creditlens_template", read_creditlens_template)
    workflow.add_node("annual_report_parser", annual_report_parser)
    workflow.add_node("source_language", source_language)
    workflow.add_node("select_pages", select_pages)
    workflow.add_node("connect_llm", connect_llm)
    workflow.add_node("build_rag_index", build_rag_index)
    workflow.add_node("answer_questions", answer_questions)
    workflow.add_node("confidence_refinement", confidence_refinement)
    workflow.add_node("create_excel_output", create_excel_output)

    workflow.add_edge(START, "read_creditlens_template")
    workflow.add_edge("read_creditlens_template", "annual_report_parser")
    workflow.add_edge("annual_report_parser", "source_language")
    workflow.add_edge("source_language", "select_pages")
    workflow.add_edge("select_pages", "connect_llm")
    workflow.add_edge("connect_llm", "build_rag_index")
    workflow.add_edge("build_rag_index", "answer_questions")
    workflow.add_edge("answer_questions", "confidence_refinement")
    workflow.add_edge("confidence_refinement", "create_excel_output")
    workflow.add_edge("create_excel_output", END)

    return workflow.compile()

set_model(build_graph())