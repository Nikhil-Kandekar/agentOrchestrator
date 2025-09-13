import os
import json
import re
import requests
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
import getpass

# Load environment variables
load_dotenv()

class MiniAgenticAISystem:
    def __init__(self):
        # Initialize Mistral AI client
        self.api_key = os.environ.get("MISTRAL_API_KEY")
        if not self.api_key:
            self.api_key = getpass.getpass("Enter your Mistral AI API key: ")
            os.environ["MISTRAL_API_KEY"] = self.api_key
            
        self.api_url = "https://api.mistral.ai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        self.memory = []  # Stores last 2 queries + results
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
            },
            {
                "campaign_id": "CAMP_C",
                "influenced_revenue": 175000,
                "impressions": 120000,
                "clicks": 3600,
                "channel": "SMS",
                "run_date": "2025-07-15"
            },
            {
                "campaign_id": "CAMP_D",
                "influenced_revenue": 90000,
                "impressions": 60000,
                "clicks": 1200,
                "channel": "Push Notification",
                "run_date": "2025-07-20"
            }
        ]
    
    def add_to_memory(self, query: str, result: Dict[str, Any]):
        """Store the last 2 queries + results in memory"""
        if len(self.memory) >= 2:
            self.memory.pop(0)
        self.memory.append({"query": query, "result": result})
    
    def get_llm_response(self, prompt: str, system_message: str = None) -> str:
        """Get response from Mistral AI LLM"""
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        try:
            payload = {
                "model": "mistral-large-latest",
                "messages": messages,
                "temperature": 0.1
            }
            
            response = requests.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error calling Mistral AI: {str(e)}"
    
    def route_query(self, query: str) -> str:
        """Determine which tool to use based on the query"""
        system_message = """You are a query routing assistant. Analyze the user's query and determine which tool to use.
        Options:
        - data_tool: For queries about revenue, campaigns, performance, CTR, etc. that require data analysis
        - reporting_tool: For queries that ask to format or report on JSON data
        - memory_tool: For queries that reference previous results like "previous", "last time", etc.
        - greeting: For greetings like "hi", "hello", "good morning"
        - fallback: For irrelevant queries
        
        Respond with only the tool name."""
        
        prompt = f"User query: {query}\n\nWhich tool should be used? Respond with only the tool name."
        return self.get_llm_response(prompt, system_message).strip().lower()
    
    def data_tool(self, query: str) -> Dict[str, Any]:
        """Simulate data analysis by generating and executing a mock query"""
        # Generate SQL or MongoDB query using LLM
        system_message = """You are a data analyst. Based on the user's query, generate an appropriate SQL query 
        that would answer the question. The available fields are: campaign_id, influenced_revenue, impressions, 
        clicks, channel, run_date. Respond with only the SQL query."""
        
        sql_query = self.get_llm_response(query, system_message)
        
        # In a real system, we would execute this query against a database
        # For this mock implementation, we'll simulate query execution by filtering the sample data
        
        # Extract conditions from SQL query for mock execution
        conditions = self.parse_sql_conditions(sql_query)
        filtered_data = self.apply_conditions(self.sample_data, conditions)
        
        # Generate summary using LLM
        summary_prompt = f"""Based on this data: {json.dumps(filtered_data, indent=2)}
        Provide a concise human-friendly summary of the results for the query: {query}"""
        
        summary = self.get_llm_response(summary_prompt, "You are a data analyst providing summaries.")
        
        return {
            "tool": "data_tool",
            "generated_query": sql_query,
            "structured_data": filtered_data,
            "summary": summary
        }
    
    def parse_sql_conditions(self, sql_query: str) -> List[Dict[str, Any]]:
        """Extract conditions from SQL query for mock execution"""
        conditions = []
        
        # Simple parsing for demonstration - in a real system, use proper SQL parsing
        if "WHERE" in sql_query.upper():
            where_clause = sql_query.upper().split("WHERE")[1]
            where_clause = where_clause.split("GROUP BY")[0] if "GROUP BY" in where_clause else where_clause
            where_clause = where_clause.split("ORDER BY")[0] if "ORDER BY" in where_clause else where_clause
            
            # Extract simple conditions (this is a simplified approach)
            conditions_str = where_clause.strip()
            conditions = self.extract_conditions(conditions_str)
        
        return conditions
    
    def extract_conditions(self, conditions_str: str) -> List[Dict[str, Any]]:
        """Extract conditions from SQL WHERE clause (simplified implementation)"""
        conditions = []
        
        # Split by AND/OR operators
        parts = re.split(r'\s+AND\s+|\s+OR\s+', conditions_str, flags=re.IGNORECASE)
        
        for part in parts:
            part = part.strip()
            if part.endswith(';'):
                part = part[:-1]
            
            # Match simple comparison patterns
            patterns = [
                r'(\w+)\s*=\s*[\'"]([^\'"]+)[\'"]',  # string equality
                r'(\w+)\s*=\s*(\d+)',  # numeric equality
                r'(\w+)\s*>\s*(\d+)',  # greater than
                r'(\w+)\s*<\s*(\d+)',  # less than
                r'(\w+)\s*LIKE\s*[\'"]([^\'"]+)[\'"]',  # LIKE pattern
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
                        value = value.replace('%', '.*')  # Convert SQL LIKE to regex
                    
                    conditions.append({
                        'field': field,
                        'operator': operator,
                        'value': value
                    })
                    break
        
        return conditions
    
    def apply_conditions(self, data: List[Dict[str, Any]], conditions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply conditions to filter data (mock query execution)"""
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
    
    def reporting_tool(self, query: str) -> Dict[str, Any]:
        """Format JSON data based on user request"""
        system_message = """You are a reporting assistant. The user will provide a query about how to format 
        or present JSON data. Respond with a well-formatted table or textual summary of the data."""
        
        # For this mock implementation, we'll use the sample data
        formatted_output = self.get_llm_response(
            f"Query: {query}\n\nData to format: {json.dumps(self.sample_data, indent=2)}",
            system_message
        )
        
        return {
            "tool": "reporting_tool",
            "formatted_output": formatted_output,
            "raw_data": self.sample_data
        }
    
    def memory_tool(self, query: str) -> Dict[str, Any]:
        """Handle queries that reference previous results"""
        if not self.memory:
            return {
                "tool": "memory_tool",
                "result": "No previous queries found in memory.",
                "summary": "I don't have any previous results to reference yet."
            }
        
        # Use LLM to understand what about previous results is being requested
        memory_context = json.dumps(self.memory, indent=2)
        prompt = f"""User query: {query}
        
        Previous queries and results: {memory_context}
        
        Based on the user's current query and the previous results, provide a helpful response.
        Focus on summarizing or analyzing the previous results as requested."""
        
        summary = self.get_llm_response(prompt, "You help users analyze previous query results.")
        
        return {
            "tool": "memory_tool",
            "previous_queries": self.memory,
            "summary": summary
        }
    
    def handle_greeting(self, query: str) -> Dict[str, Any]:
        """Handle greetings"""
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
        
        if any(greeting in query.lower() for greeting in greetings):
            response = "Hello! I'm your data analytics assistant. How can I help you today?"
        else:
            response = "I can help with campaign analytics queries like revenue, performance, CTR, etc."
        
        return {
            "tool": "greeting",
            "response": response
        }
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """Main method to process user queries"""
        # Route the query to appropriate tool
        tool = self.route_query(query)
        
        # Handle based on tool selection
        if "data_tool" in tool:
            result = self.data_tool(query)
        elif "reporting_tool" in tool:
            result = self.reporting_tool(query)
        elif "memory_tool" in tool:
            result = self.memory_tool(query)
        elif "greeting" in tool:
            result = self.handle_greeting(query)
        else:
            result = {
                "tool": "fallback",
                "response": "I can help with campaign analytics queries like revenue, performance, CTR, etc."
            }
        
        # Add to memory if it's a data or reporting query
        if result["tool"] in ["data_tool", "reporting_tool"]:
            self.add_to_memory(query, result)
        
        return result

# Example usage
if __name__ == "__main__":
    # Initialize the system
    agent = MiniAgenticAISystem()
    
    # Example queries
    queries = [
        "Show me revenue by channel for July 2025",
        "Show me Top 3 performing campaigns",
        "Format this JSON data as a table",
        "Summarize the previous results",
        "Hi there!",
        "What's the weather like today?"
    ]
    
    # Process each query
    for query in queries:
        print(f"\n=== Query: {query} ===")
        result = agent.process_query(query)
        print(f"Tool used: {result['tool']}")
        
        if result['tool'] == 'data_tool':
            print(f"Generated query: {result['generated_query']}")
            print(f"Summary: {result['summary']}")
            print(f"Structured data (first few items): {json.dumps(result['structured_data'][:2], indent=2) if result['structured_data'] else 'No data found'}")
        elif result['tool'] == 'reporting_tool':
            print(f"Formatted output: {result['formatted_output']}")
        elif result['tool'] == 'memory_tool':
            print(f"Summary: {result['summary']}")
        else:
            print(f"Response: {result['response']}")