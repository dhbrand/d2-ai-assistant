import PyPDF2
import re

def read_d2_checklist():
    with open('D2 Checklist.pdf', 'rb') as file:
        # Create a PDF reader object
        pdf_reader = PyPDF2.PdfReader(file)
        
        # Get the text from all pages
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        
        # Split into lines and clean up
        lines = text.split('\n')
        
        # Find the Exotic Catalysts section
        catalyst_section = False
        catalysts = []
        current_catalyst = {}
        
        for line in lines:
            # Clean up the line
            line = line.strip()
            
            # Look for section start
            if "Exotic Catalysts" in line:
                catalyst_section = True
                continue
            
            if catalyst_section:
                # Look for catalyst entries (they usually end in "Catalyst" or have progress indicators)
                if "Catalyst" in line or "%" in line:
                    if current_catalyst:
                        catalysts.append(current_catalyst)
                        current_catalyst = {}
                    
                    # Extract name and progress
                    current_catalyst['name'] = line.split('%')[0] if '%' in line else line
                    if '%' in line:
                        current_catalyst['progress'] = line.split('%')[0].split()[-1] + '%'
                
                # Look for objectives
                elif "Objectives:" in line:
                    current_catalyst['objectives'] = line
                
                # Look for description
                elif current_catalyst and 'description' not in current_catalyst:
                    current_catalyst['description'] = line
        
        # Add the last catalyst if there is one
        if current_catalyst:
            catalysts.append(current_catalyst)
        
        # Print catalysts in a formatted way
        print("\nFound Catalysts:")
        print("================")
        for catalyst in catalysts:
            print(f"\nName: {catalyst.get('name', 'Unknown')}")
            if 'progress' in catalyst:
                print(f"Progress: {catalyst['progress']}")
            if 'description' in catalyst:
                print(f"Description: {catalyst['description']}")
            if 'objectives' in catalyst:
                print(f"Objectives: {catalyst['objectives']}")
            print("-" * 50)

if __name__ == "__main__":
    read_d2_checklist() 