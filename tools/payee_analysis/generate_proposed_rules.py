#!/usr/bin/env python3
"""
Generate payee consolidation rules using OpenAI analysis.

Takes the payee analysis data and generates specific consolidation rules
in the format: "If payee contains 'Dark Arts' then set payee to 'Dark Arts'"
"""

import json
import logging
import os
import openai
import google.generativeai as genai
from dotenv import load_dotenv
from modules.config import ENVs

def load_payee_analysis():
    """Load the payee analysis data."""
    try:
        with open('payee_analysis_for_openai.txt', 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise ValueError(
            "payee_analysis_for_openai.txt not found. Run "
            "tools/payee_analysis/analyze_payees.py first."
        )

def create_consolidation_prompt(analysis_data):
    """Create the OpenAI prompt for generating consolidation rules."""
    prompt = f"""You are analyzing bank transaction payee names to create consolidation rules. Your task is to identify groups of similar payee names that represent the same business or entity and create rules to standardize them.

ANALYSIS DATA:
{analysis_data}

INSTRUCTIONS:
1. Look for patterns in payee names that clearly represent the same business/entity
2. Common patterns include:
   - Different locations of the same chain (e.g., "NEW WORLD AUCKLAND" vs "NEW WORLD WELLINGTON")
   - Different transaction codes/suffixes (e.g., "COUNTDOWN 123456" vs "COUNTDOWN 789012")
   - Variations in formatting (e.g., "McDonald's" vs "MCDONALDS")
   - Date/location suffixes (e.g., "SHELL PETROL STATION AKL" vs "SHELL PETROL STATION WLG")

3. For each group of similar payees, create ONE consolidation rule in this EXACT format:
   If payee contains "[key_identifier]" then set payee to "[standardized_name]"

4. CRITICAL: Create only ONE rule per business/entity. Do NOT create multiple rules that would match the same payees.
5. Use the most specific core business name that uniquely identifies the business (not the shortest possible string)
   Think of it as dropping extraneous words like locations, codes, prefixes until you have the core business name - then stop
6. Choose the most common or clearest name as the standardized version
7. Focus on high-frequency payees first, but don't ignore consolidation opportunities in lower-frequency ones
8. Group by category where it makes sense (e.g., all supermarkets together)

AVOID DUPLICATES:
- If you see "PAYPAL *ICEBREAKER" and "ICEBREAKER ONLINE", use only "ICEBREAKER" 
- If you see "SP THUNDERPANTS" and "THUNDERPANTS STORE", use only "THUNDERPANTS"
- Choose the identifier that captures the most variations with a single rule

CRITICAL: It's not always obvious and you need to think.  There might be a common prefix.
For example "PAYPAL *MERCHANT", tells you PAYPAL is the payment processor which is irrelevant.
The actual business is MERCHANT, not PayPal.

This could apply to the prefix (SP, PAYPAL *, DIRECT DEBIT -) or suffix (LIMIT, NZL, etc).

BAD EXAMPLES - DO NOT DO THIS:
If payee contains "F" then set payee to "Flick Energy" (too generic - matches everything)
If payee contains "THE" then set payee to "The Warehouse" (too common)
If payee contains "NEW" then set payee to "New World" (too generic)

GOOD EXAMPLES (extract the core business name):
Given "NEW WORLD AUCKLAND NZL": If payee contains "NEW WORLD" then set payee to "New World"
Given "MCDONALDS QUEEN ST": If payee contains "MCDONALDS" then set payee to "McDonald's"  
Given "PAYPAL *ICEBREAKER": If payee contains "ICEBREAKER" then set payee to "Icebreaker"
Given "DIRECT DEBIT -FLICK ENERGY LIMIT": If payee contains "FLICK ENERGY" then set payee to "Flick Energy"

Generate consolidation rules for the payee data provided. Focus on clear, obvious consolidations first."""

    return prompt

def call_ai_api(prompt):
    """Call AI API (OpenAI or Gemini) to generate consolidation rules."""
    ai_provider = os.getenv('AI_PROVIDER', 'openai').lower()
    
    if ai_provider == 'gemini':
        return call_gemini_api(prompt)
    else:
        return call_openai_api(prompt)

def call_gemini_api(prompt):
    """Call Gemini API to generate consolidation rules."""
    gemini_key = os.getenv('GEMINI_API_KEY')
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    
    genai.configure(api_key=gemini_key)
    logging.info("Calling Gemini API to generate consolidation rules...")
    
    model = genai.GenerativeModel('gemini-1.5-pro')
    
    system_prompt = "You are a financial data analyst specializing in payee name standardization."
    full_prompt = f"{system_prompt}\n\n{prompt}"
    
    response = model.generate_content(
        full_prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=16000,
            temperature=0.1
        )
    )
    
    return response.text

def call_openai_api(prompt):
    """Call OpenAI API to generate consolidation rules."""
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    
    openai.api_key = openai_key
    
    logging.info("Calling OpenAI API to generate consolidation rules...")
    
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a financial data analyst specializing in payee name standardization."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=16000,
        temperature=0.1  # Low temperature for consistent, logical output
    )
    
    return response.choices[0].message.content

def parse_consolidation_rules(openai_response):
    """Parse the OpenAI response into structured consolidation rules."""
    rules = []
    lines = openai_response.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if line.startswith('If payee contains'):
            # Parse: If payee contains "X" then set payee to "Y"
            try:
                # Find the parts between double quotes
                parts = line.split('"')
                if len(parts) >= 4:
                    contains_text = parts[1]
                    standardized_name = parts[3]
                    rules.append({
                        'contains': contains_text,
                        'standardized_name': standardized_name,
                        'rule_text': line
                    })
            except Exception as e:
                logging.warning(f"Could not parse rule line: {line} - {e}")
                continue
    
    return rules

def save_consolidation_rules(rules, openai_response):
    """Save the consolidation rules to files."""
    # Save raw OpenAI response
    with open('openai_response.txt', 'w') as f:
        f.write(openai_response)
    
    # Save as JSON for programmatic use
    with open('proposed_consolidation_rules.json', 'w') as f:
        json.dump(rules, f, indent=2)
    
    # Save as text for human review
    with open('proposed_consolidation_rules.txt', 'w') as f:
        f.write("PROPOSED PAYEE CONSOLIDATION RULES\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Generated {len(rules)} consolidation rules:\n\n")
        
        for i, rule in enumerate(rules, 1):
            f.write(f"{i:3d}. {rule['rule_text']}\n")
    
    logging.info(f"Saved {len(rules)} consolidation rules to proposed_consolidation_rules.json and .txt")

def main():
    """Main function to generate consolidation rules."""
    logging.basicConfig(level=logging.INFO)
    
    # Load environment variables
    load_dotenv()
    
    # Load payee analysis data
    analysis_data = load_payee_analysis()
    logging.info("Loaded payee analysis data")
    
    # Create OpenAI prompt
    prompt = create_consolidation_prompt(analysis_data)
    
    # Display the prompt
    print("=" * 80)
    print("PROMPT TO BE SENT TO OPENAI:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)
    print(f"Prompt length: {len(prompt)} characters")
    print(f"Estimated tokens: ~{len(prompt)//4}")
    print("=" * 80)
    
    # Ask for confirmation
    response = input("\nProceed with OpenAI API call? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        return None
    
    # Call AI API
    ai_response = call_ai_api(prompt)
    
    # Parse the response into structured rules
    logging.info(f"AI response received ({len(ai_response)} characters)")
    logging.info(f"First 500 chars of response: {ai_response[:500]}")
    
    rules = parse_consolidation_rules(ai_response)
    
    if not rules:
        logging.error("No valid consolidation rules found in AI response")
        logging.error(f"Full AI response:\n{ai_response}")
        raise ValueError("No valid consolidation rules found in AI response")
    
    # Save the rules
    save_consolidation_rules(rules, ai_response)
    
    logging.info("Consolidation rule generation complete!")
    return rules

if __name__ == "__main__":
    main()
