import os
import json
import re
from typing import Dict, List, Any, Optional, TypedDict
from dotenv import load_dotenv
import getpass

# LangChain imports
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_mistralai import ChatMistralAI
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.prompts import ChatPromptTemplate

# Load environment variables
load_dotenv()

class AgentState(TypedDict):
    """State for the agentic system"""
    messages: List[Any]
    query: str
    tool: Optional[str]
    result: Optional[Dict[str, Any]]
    json_data: Optional[Any]
    memory: List[Dict[str, Any]]

class MiniAgenticAISystem:
    def __init__(self):
        # Initialize Mistral AI client
        self.api_key = os.environ.get("MISTRAL_API_KEY")
        if not self.api_key:
            self.api_key = getpass.getpass("Enter your Mistral AI API key: ")
            os.environ["MISTRAL_API_KEY"] = self.api_key
        
        # Initialize LangChain components
        self.llm = ChatMistralAI(
            model="mistral-large-latest",
            temperature=0.1,
            api_key=self.api_key
        )
        self.output_parser = StrOutputParser()
        
        # Sample data for demonstration
        self.sample_data = [
            {
                "campaign_id": "CAMP_A",
                "influenced_revenue": 150000,
                "impressions": 100000,
                "clicks": 2500,
                "channel": "WhatsApp",
                "run_date": "2025-07-05"
            },
            {
                "campaign_id": "CAMP_B",
                "influenced_revenue": 200000,
                "impressions": 80000,
                "clicks": 4000,
                "channel": "Email",
                "run_date": "2025-07-10"
            }
        ]
        
        # Build the LangGraph
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the LangGraph state machine"""
        workflow = StateGraph(AgentState)
        
        # Define nodes
        workflow.add_node("extract_json", self.extract_json_node)
        workflow.add_node("route_query", self.route_query_node)
        workflow.add_node("process_data_tool", self.process_data_tool_node)
        workflow.add_node("process_reporting_tool", self.process_reporting_tool_node)
        workflow.add_node("process_memory_tool", self.process_memory_tool_node)
        workflow.add_node("process_greeting", self.process_greeting_node)
        workflow.add_node("process_fallback", self.process_fallback_node)
        workflow.add_node("update_memory", self.update_memory_node)
        
        # Define edges
        workflow.set_entry_point("extract_json")
        workflow.add_edge("extract_json", "route_query")
        
        # Conditional routing
        workflow.add_conditional_edges(
            "route_query",
            self.route_condition,
            {
                "data_tool": "process_data_tool",
                "reporting_tool": "process_reporting_tool",
                "memory_tool": "process_memory_tool",
                "greeting": "process_greeting",
                "fallback": "process_fallback"
            }
        )
        
        # Connect tool processing to memory update
        workflow.add_edge("process_data_tool", "update_memory")
        workflow.add_edge("process_reporting_tool", "update_memory")
        workflow.add_edge("process_memory_tool", END)
        workflow.add_edge("process_greeting", END)
        workflow.add_edge("process_fallback", END)
        workflow.add_edge("update_memory", END)
        
        return workflow.compile()
    
    def extract_json_node(self, state: AgentState) -> AgentState:
        """Extract JSON data from query"""
        query = state["query"]
        json_data = self.extract_json_from_query(query)
        
        return {
            **state,
            "json_data": json_data
        }
    
    def route_query_node(self, state: AgentState) -> AgentState:
        """Route query to appropriate tool"""
        query = state["query"]
        json_data = state["json_data"]
        
        # System prompt for routing
        system_message = """You are a query routing assistant. Analyze the user's query and determine which tool to use.
        Options:
        - data_tool: For queries about revenue, campaigns, performance, CTR, etc. that require data analysis
        - reporting_tool: For queries that ask to format or report on JSON data
        - memory_tool: For queries that reference previous results like "previous", "last time", etc.
        - greeting: For greetings like "hi", "hello", "good morning"
        - fallback: For irrelevant queries
        
        Respond with only the tool name."""
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", "User query: {query}\n\nWhich tool should be used? Respond with only the tool name.")
        ])
        
        # Create chain
        chain = prompt | self.llm | self.output_parser
        
        # Get response
        tool = chain.invoke({"query": query}).strip().lower()
        
        # If JSON is present, prefer reporting tool
        if json_data and "reporting" not in tool:
            tool = "reporting_tool"
        
        return {
            **state,
            "tool": tool
        }
    
    def route_condition(self, state: AgentState) -> str:
        """Conditional routing based on tool selection"""
        return state["tool"]
    
    def process_data_tool_node(self, state: AgentState) -> AgentState:
        """Process data analysis queries"""
        query = state["query"]
        
        # Generate SQL query
        sql_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a data analyst. Based on the user's query, generate an appropriate SQL query 
            that would answer the question. The available fields are: campaign_id, influenced_revenue, impressions, 
            clicks, channel, run_date. Respond with only the SQL query."""),
            ("human", "{query}")
        ])
        
        sql_chain = sql_prompt | self.llm | self.output_parser
        sql_query = sql_chain.invoke({"query": query})
        
        # Mock query execution
        conditions = self.parse_sql_conditions(sql_query)
        filtered_data = self.apply_conditions(self.sample_data, conditions)
        
        # Generate summary
        summary_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a data analyst providing concise human-friendly summaries."),
            ("human", """Based on this data: {data}
            Provide a concise human-friendly summary of the results for the query: {query}""")
        ])
        
        summary_chain = summary_prompt | self.llm | self.output_parser
        summary = summary_chain.invoke({
            "data": json.dumps(filtered_data, indent=2),
            "query": query
        })
        
        result = {
            "tool": "data_tool",
            "generated_query": sql_query,
            "structured_data": filtered_data,
            "summary": summary
        }
        
        return {
            **state,
            "result": result
        }
    
    def process_reporting_tool_node(self, state: AgentState) -> AgentState:
        """Process reporting queries"""
        query = state["query"]
        json_data = state["json_data"]
        
        # Use sample data if no JSON provided
        if json_data is None:
            json_data = self.sample_data
            data_source = "sample data (no JSON provided in query)"
        else:
            data_source = "JSON data from your query"
        
        # Format data
        reporting_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a reporting assistant specialized in formatting JSON data into clear, readable tables.
            Respond with a well-formatted table using markdown-style formatting with clear headers.
            If the data is complex, provide a summary first followed by the detailed table.
            Make sure to include all relevant metrics and format numbers appropriately."""),
            ("human", """User query: {query}
            
            JSON data to format: {json_data}""")
        ])
        
        reporting_chain = reporting_prompt | self.llm | self.output_parser
        formatted_output = reporting_chain.invoke({
            "query": query,
            "json_data": json.dumps(json_data, indent=2)
        })
        
        result = {
            "tool": "reporting_tool",
            "formatted_output": formatted_output,
            "data_source": data_source,
            "raw_data": json_data
        }
        
        return {
            **state,
            "result": result
        }
    
    def process_memory_tool_node(self, state: AgentState) -> AgentState:
        """Process memory-related queries"""
        memory = state.get("memory", [])
        
        if not memory:
            result = {
                "tool": "memory_tool",
                "result": "No previous queries found in memory.",
                "summary": "I don't have any previous results to reference yet."
            }
        else:
            memory_prompt = ChatPromptTemplate.from_messages([
                ("system", "You help users analyze previous query results."),
                ("human", """User query: {query}
                
                Previous queries and results: {memory_context}
                
                Based on the user's current query and the previous results, provide a helpful response.
                Focus on summarizing or analyzing the previous results as requested.""")
            ])
            
            memory_chain = memory_prompt | self.llm | self.output_parser
            summary = memory_chain.invoke({
                "query": state["query"],
                "memory_context": json.dumps(memory, indent=2)
            })
            
            result = {
                "tool": "memory_tool",
                "previous_queries": memory,
                "summary": summary
            }
        
        return {
            **state,
            "result": result
        }
    
    def process_greeting_node(self, state: AgentState) -> AgentState:
        """Process greetings"""
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
        query = state["query"].lower()
        
        if any(greeting in query for greeting in greetings):
            response = "Hello! I'm your data analytics assistant. How can I help you today?"
        else:
            response = "I can help with campaign analytics queries like revenue, performance, CTR, etc."
        
        result = {
            "tool": "greeting",
            "response": response
        }
        
        return {
            **state,
            "result": result
        }
    
    def process_fallback_node(self, state: AgentState) -> AgentState:
        """Process fallback queries"""
        result = {
            "tool": "fallback",
            "response": "I can help with campaign analytics queries like revenue, performance, CTR, etc."
        }
        
        return {
            **state,
            "result": result
        }
    
    def update_memory_node(self, state: AgentState) -> AgentState:
        """Update memory with current query and result"""
        memory = state.get("memory", [])
        query = state["query"]
        result = state["result"]
        
        # Store last 2 queries + results
        if result["tool"] in ["data_tool", "reporting_tool"]:
            if len(memory) >= 2:
                memory.pop(0)
            memory.append({"query": query, "result": result})
        
        return {
            **state,
            "memory": memory
        }
    
    def extract_json_from_query(self, query: str) -> Any:
        """Extract JSON data from the query string if present"""
        json_patterns = [
            r'\{.*\}',  # Basic JSON object pattern
            r'\[.*\]',  # Basic JSON array pattern
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, query, re.DOTALL)
            if matches:
                for match in matches:
                    try:
                        return json.loads(match)
                    except json.JSONDecodeError:
                        try:
                            cleaned_match = match.strip()
                            if cleaned_match.endswith(','):
                                cleaned_match = cleaned_match[:-1]
                            return json.loads(cleaned_match)
                        except json.JSONDecodeError:
                            continue
        return None
    
    def parse_sql_conditions(self, sql_query: str) -> List[Dict[str, Any]]:
        """Extract conditions from SQL query for mock execution"""
        conditions = []
        
        if "WHERE" in sql_query.upper():
            where_clause = sql_query.upper().split("WHERE")[1]
            where_clause = where_clause.split("GROUP BY")[0] if "GROUP BY" in where_clause else where_clause
            where_clause = where_clause.split("ORDER BY")[0] if "ORDER BY" in where_clause else where_clause
            
            conditions_str = where_clause.strip()
            conditions = self.extract_conditions(conditions_str)
        
        return conditions
    
    def extract_conditions(self, conditions_str: str) -> List[Dict[str, Any]]:
        """Extract conditions from SQL WHERE clause"""
        conditions = []
        parts = re.split(r'\s+AND\s+|\s+OR\s+', conditions_str, flags=re.IGNORECASE)
        
        for part in parts:
            part = part.strip()
            if part.endswith(';'):
                part = part[:-1]
            
            patterns = [
                r'(\w+)\s*=\s*[\'"]([^\'"]+)[\'"]',
                r'(\w+)\s*=\s*(\d+)',
                r'(\w+)\s*>\s*(\d+)',
                r'(\w+)\s*<\s*(\d+)',
                r'(\w+)\s*LIKE\s*[\'"]([^\'"]+)[\'"]',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, part, re.IGNORECASE)
                if match:
                    field, value = match.groups()
                    operator = '='
                    if '>' in part:
                        operator = '>'
                    elif '<' in part:
                        operator = '<'
                    elif 'LIKE' in part.upper():
                        operator = 'LIKE'
                        value = value.replace('%', '.*')
                    
                    conditions.append({
                        'field': field,
                        'operator': operator,
                        'value': value
                    })
                    break
        
        return conditions
    
    def apply_conditions(self, data: List[Dict[str, Any]], conditions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply conditions to filter data"""
        if not conditions:
            return data
        
        filtered_data = []
        for item in data:
            matches_all = True
            for condition in conditions:
                field = condition['field']
                operator = condition['operator']
                value = condition['value']
                
                if field not in item:
                    matches_all = False
                    break
                
                if operator == '=':
                    if str(item[field]) != value:
                        matches_all = False
                        break
                elif operator == '>':
                    if not (isinstance(item[field], (int, float)) and item[field] > float(value)):
                        matches_all = False
                        break
                elif operator == '<':
                    if not (isinstance(item[field], (int, float)) and item[field] < float(value)):
                        matches_all = False
                        break
                elif operator == 'LIKE':
                    pattern = re.compile(value, re.IGNORECASE)
                    if not pattern.search(str(item[field])):
                        matches_all = False
                        break
            
            if matches_all:
                filtered_data.append(item)
        
        return filtered_data
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """Main method to process user queries"""
        # Initialize state
        initial_state = AgentState(
            messages=[],
            query=query,
            tool=None,
            result=None,
            json_data=None,
            memory=[]
        )
        
        # Execute the graph
        final_state = self.graph.invoke(initial_state)
        
        return final_state["result"]

# Example usage with chatbot interface
if __name__ == "__main__":
    # Initialize the system
    agent = MiniAgenticAISystem()
    
    print("=" * 60)
    print("Welcome to the Campaign Analytics Chatbot!")
    print("I can help you analyze marketing campaign data.")
    print("You can paste JSON data directly in your query to format it as a table.")
    print("Type 'quit', 'exit', or 'bye' to end the conversation.")
    print("=" * 60)
    
    memory = []
    
    while True:
        # Get user input
        query = input("\nYou: ").strip()
        
        # Check for exit conditions
        if query.lower() in ['quit', 'exit', 'bye', 'goodbye']:
            print("Chatbot: Thank you for using the Campaign Analytics Chatbot. Goodbye!")
            break
            
        # Skip empty queries
        if not query:
            continue
        
        # Process the query
        result = agent.process_query(query)
        
        # Display the response based on the tool used
        print(f"\nChatbot: ", end="")
        
        if result['tool'] == 'data_tool':
            print(result['summary'])
            if result['structured_data']:
                print(f"\nI found {len(result['structured_data'])} matching campaigns.")
                if len(result['structured_data']) <= 3:
                    print("Here are the details:")
                    for item in result['structured_data']:
                        print(f"  - {item['campaign_id']}: {item['channel']} campaign with ${item['influenced_revenue']:,.0f} revenue")
        elif result['tool'] == 'reporting_tool':
            print(f"Using {result['data_source']}:")
            print(result['formatted_output'])
        elif result['tool'] == 'memory_tool':
            print(result['summary'])
        elif result['tool'] == 'greeting':
            print(result['response'])
        else:
            print(result['response'])
            
        # Add a small separator for readability
        print("-" * 40)