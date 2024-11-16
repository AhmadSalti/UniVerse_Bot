from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
import requests  # or your preferred HTTP library

class ActionGetSubjectDescription(Action):
    def name(self) -> Text:
        return "action_get_subject_description"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Get the subject entity from the user's message
        subject = tracker.get_slot('subject')
        
        if subject:
            try:
                # Make API call to your database
                response = requests.get(f"your_api_endpoint/subjects/{subject}")
                
                if response.status_code == 200:
                    subject_data = response.json()
                    description = subject_data.get('description')
                    response_text = f"وصف مادة {subject}: {description}"
                else:
                    response_text = f"عذراً، لا يوجد لدي معلومات عن مادة {subject}"
                    
            except Exception as e:
                response_text = "عذراً، حدث خطأ في استرجاع المعلومات"
        else:
            response_text = "عذراً، لم أفهم اسم المادة. هل يمكنك إعادة صياغة السؤال؟"
            