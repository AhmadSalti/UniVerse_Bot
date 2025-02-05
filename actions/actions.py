from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rapidfuzz import fuzz, process
import requests
import re
from .config import ENDPOINTS
import jwt


def normalize_arabic_text(text: str) -> str:
        if not text:
            return text

        if "النمذجة" in text:
            return text
        
        text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
        
        text = re.sub('[إأآىئءا]', 'ا', text)
        
        text = text.replace('ة', 'ه')
        
        text = re.sub(r'ال(?=\w)', '', text)
        
        text = re.sub(r'[^\u0621-\u064A0-9 ]', '', text)
        
        return ' '.join(text.split()).strip()

def get_best_subject_match(normalized_input: str, subject_names: dict) -> tuple:

    synonyms = {
        "تراسل 1": "تراسل المعطيات وشبكات الحواسيب 1",
        "تراسل": "تراسل المعطيات وشبكات الحواسيب 1",
        "تراسل 2": "تراسل المعطيات وشبكات الحواسيب 2",
        "عربي": "اللغة العربية 1",
        "عربي 1": "اللغة العربية 1",
        "عربي 2": "اللغة العربية 2"
    }
    
    normalized_input = normalize_arabic_text(normalized_input)
    
    if normalized_input in synonyms:
        target_name = synonyms[normalized_input]
        normalized_target = normalize_arabic_text(target_name)
        
        best_match = None
        best_ratio = 0
        for subject_name in subject_names.keys():
            normalized_subject = normalize_arabic_text(subject_name)
            ratio = fuzz.ratio(normalized_subject, normalized_target)
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = subject_name
        
        if best_ratio > 60:
            return (best_match, best_ratio)
    
    input_number = None
    for char in normalized_input:
        if char.isdigit():
            input_number = char
            break
    
    matches = process.extract(
        normalized_input,
        subject_names.keys(),
        scorer=fuzz.WRatio,
        limit=3
    )
    
    if input_number:
        numbered_matches = [
            match for match in matches 
            if input_number in match[0]
        ]
        
        if numbered_matches:
            return numbered_matches[0]
    for match in matches:
        if match[1] >= 60:
            return match
    return None

class ActionGetSubjectDescription(Action):
    def name(self) -> Text:
        return "action_get_subject_description"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        subject = next((entity['value'] for entity in tracker.latest_message.get('entities', []) 
                       if entity['entity'] == 'subject'), None)
        
        if not subject:
            subject = tracker.get_slot('subject')
            if not subject:
                dispatcher.utter_message(text="عذراً، لم تحدد المادة التي تريد معرفة معلومات عنها. الرجاء ذكر اسم المادة")
                return []
        
        try:
            response = requests.get(ENDPOINTS["get_all_subjects"])
            
            if response.status_code == 200:
                subjects = response.json()
                normalized_input = normalize_arabic_text(subject)
                
                subject_names = {normalize_arabic_text(s['name']): s for s in subjects}
                
                best_match_name = get_best_subject_match(normalized_input, subject_names)
                
                if best_match_name:
                    best_match = subject_names[best_match_name[0]]
                    description = best_match.get('description', 'لا يوجد وصف متوفر')
                    
                    combined_message = f"مادة {best_match['name']} تشمل:{description}"
                    dispatcher.utter_message(text=combined_message)
                    
                    dispatcher.utter_message(response="utter_did_that_help")
                    return [SlotSet("subject", best_match['name'])]
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetSubjectHours(Action):
    def name(self) -> Text:
        return "action_get_subject_hours"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        subject = next((entity['value'] for entity in tracker.latest_message.get('entities', []) 
                       if entity['entity'] == 'subject'), None)
        
        if not subject:
            subject = tracker.get_slot('subject')
            if not subject:
                dispatcher.utter_message(text="عذراً، لم تحدد المادة التي تريد معرفة ساعاتها. الرجاء ذكر اسم المادة")
                return []

        try:
            response = requests.get(ENDPOINTS["get_all_subjects"])
            
            if response.status_code == 200:
                subjects = response.json()
                normalized_input = normalize_arabic_text(subject)
                
                subject_names = {normalize_arabic_text(s['name']): s for s in subjects}
                
                best_match_name = process.extractOne(
                    normalized_input,
                    subject_names.keys(),
                    scorer=fuzz.WRatio,
                    score_cutoff=75
                )
                
                if best_match_name:
                    best_match = subject_names[best_match_name[0]]
                    hours = best_match.get('hours', 'غير محدد')
                    
                    combined_message = f"عدد ساعات مادة {best_match['name']} هو {hours} ساعات"
                    dispatcher.utter_message(text=combined_message)
                    
                    dispatcher.utter_message(response="utter_did_that_help")
                    return [SlotSet("subject", best_match['name'])]
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetSubjectPractical(Action):
    def name(self) -> Text:
        return "action_get_subject_practical"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        subject = next((entity['value'] for entity in tracker.latest_message.get('entities', []) 
                       if entity['entity'] == 'subject'), None)
        
        if not subject:
            subject = tracker.get_slot('subject')
            if not subject:
                dispatcher.utter_message(text="عذراً، لم تحدد المادة التي تريد معرفة معلومات عن جلساتها العملية. الرجاء ذكر اسم المادة")
                return []

        try:
            response = requests.get(ENDPOINTS["get_all_subjects"])
            
            if response.status_code == 200:
                subjects = response.json()
                normalized_input = normalize_arabic_text(subject)
                
                subject_names = {normalize_arabic_text(s['name']): s for s in subjects}
                
                best_match_name = process.extractOne(
                    normalized_input,
                    subject_names.keys(),
                    scorer=fuzz.WRatio,
                    score_cutoff=75
                )
                
                if best_match_name:
                    best_match = subject_names[best_match_name[0]]
                    has_practical = best_match.get('hasPractical', False)
                    if has_practical:
                        dispatcher.utter_message(response="utter_get_subject_practical",
                                              subject=best_match['name'])
                    else:
                        dispatcher.utter_message(response="utter_get_subject_no_practical",
                                              subject=best_match['name'])
                    dispatcher.utter_message(response="utter_did_that_help")
                    return [SlotSet("subject", best_match['name'])]
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []

class ActionGetSubjectPrerequisites(Action):
    def name(self) -> Text:
        return "action_get_subject_prerequisites"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        subject = next((entity['value'] for entity in tracker.latest_message.get('entities', []) 
                       if entity['entity'] == 'subject'), None)
        
        if not subject:
            subject = tracker.get_slot('subject')
            if not subject:
                dispatcher.utter_message(text="عذراً، لم تحدد المادة التي تريد معرفة متطلباتها. الرجاء ذكر اسم المادة")
                return []

        try:
            response = requests.get(ENDPOINTS["get_all_subjects"])
            
            if response.status_code == 200:
                subjects = response.json()
                normalized_input = normalize_arabic_text(subject)
                
                subject_names = {normalize_arabic_text(s['name']): s for s in subjects}
                
                best_match_name = process.extractOne(
                    normalized_input,
                    subject_names.keys(),
                    scorer=fuzz.WRatio,
                    score_cutoff=75
                )
                
                if best_match_name:
                    best_match = subject_names[best_match_name[0]]
                    prerequisites = best_match.get('prerequisites', [])
                    if isinstance(prerequisites, str):
                        prereq_list = prerequisites
                    else:
                        prereq_list = "، ".join(str(prereq) for prereq in prerequisites) if prerequisites else 'لا يوجد متطلبات سابقة'
                    
                    combined_message = f"متطلبات مادة {best_match['name']} هي: {prereq_list}"
                    dispatcher.utter_message(text=combined_message)
                    
                    dispatcher.utter_message(response="utter_did_that_help")
                    return [SlotSet("subject", best_match['name'])]
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []

class ActionGetSubjectUnlocks(Action):
    def name(self) -> Text:
        return "action_get_subject_unlocks"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        subject = next((entity['value'] for entity in tracker.latest_message.get('entities', []) 
                       if entity['entity'] == 'subject'), None)
        
        if not subject:
            subject = tracker.get_slot('subject')
            if not subject:
                dispatcher.utter_message(text="عذراً، لم تحدد المادة التي تريد معرفة المواد التي تعتمد عليها. الرجاء ذكر اسم المادة")
                return []

        try:
            response = requests.get(ENDPOINTS["get_all_subjects"])
            
            if response.status_code == 200:
                subjects = response.json()
                normalized_input = normalize_arabic_text(subject)
                
                subject_names = {normalize_arabic_text(s['name']): s for s in subjects}
                
                best_match_name = process.extractOne(
                    normalized_input,
                    subject_names.keys(),
                    scorer=fuzz.WRatio,
                    score_cutoff=75
                )
                
                if best_match_name:
                    best_match = subject_names[best_match_name[0]]
                    required_for = best_match.get('requiredFor', [])
                    if isinstance(required_for, str):
                        unlocks_list = required_for
                    else:
                        unlocks_list = "، ".join(str(subject) for subject in required_for) if required_for else 'لا توجد مواد'
                    
                    combined_message = f"المواد التي تعتمد على مادة {best_match['name']} هي: {unlocks_list}"
                    dispatcher.utter_message(text=combined_message)
                    
                    dispatcher.utter_message(response="utter_did_that_help")
                    return [SlotSet("subject", best_match['name'])]
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetBranchInfo(Action):
    def name(self) -> Text:
        return "action_get_branch_info"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        branch = next((entity['value'] for entity in tracker.latest_message.get('entities', []) 
                    if entity['entity'] == 'branch'), None)
        
        if not branch:
            dispatcher.utter_message(text="عذراً، لم أفهم أي اختصاص تسأل عنه. هل يمكنك إعادة صياغة السؤال؟")
            return []
        
        if any(term in branch for term in ["ذكاء", "صنعي", "اصطناعي", "ai"]):
            dispatcher.utter_message(response="utter_branch_ai")
            
        elif any(term in branch for term in ["هندسة برمجيات", "البرمجيات", "برمجيات", "هندسة البرمجيات", "هندسة نظم المعلومات والبرمجيات"]):
            dispatcher.utter_message(response="utter_branch_se")
            
        elif any(term in branch for term in ["شبكات", "هندسة شبكات", "الشبكات", "هندسة الشبكات", "شبكات الحاسوب"]):
            dispatcher.utter_message(response="utter_branch_networks")
        
        else:
            dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن هذا الاختصاص")
            
        return []
    
class ActionListAllSubjects(Action):
    def name(self) -> Text:
        return "action_list_all_subjects"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        try:
            response = requests.get(ENDPOINTS["get_all_subjects"])
            
            if response.status_code == 200:
                subjects = response.json()
                
                if not subjects:
                    dispatcher.utter_message(text="عذراً، لا توجد مواد متوفرة حالياً")
                    return []
                
                subject_names = [subject.get('name', '') for subject in subjects if subject.get('name')]
                
                if not subject_names:
                    dispatcher.utter_message(text="عذراً، حدث خطأ في قراءة أسماء المواد")
                    return []
                
                subject_list = "\n".join([f"- {subject}" for subject in subject_names])
                response_text = f"قائمة جميع المواد المتوفرة:\n{subject_list}"
                dispatcher.utter_message(text=response_text)
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetSubjectTeacher(Action):
    def name(self) -> Text:
        return "action_get_subject_teacher"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        subject = next((entity['value'] for entity in tracker.latest_message.get('entities', []) 
                       if entity['entity'] == 'subject'), None)
        
        if not subject:
            subject = tracker.get_slot('subject')
            if not subject:
                dispatcher.utter_message(text="عذراً، لم تحدد المادة التي تريد معرفة مدرسها. الرجاء ذكر اسم المادة")
                return []

        try:
            response = requests.get(ENDPOINTS["get_all_subjects"])
            
            if response.status_code == 200:
                subjects = response.json()
                normalized_input = normalize_arabic_text(subject)
                
                subject_names = {normalize_arabic_text(s['name']): s for s in subjects}
                
                best_match_name = process.extractOne(
                    normalized_input,
                    subject_names.keys(),
                    scorer=fuzz.WRatio,
                    score_cutoff=75
                )
                
                if best_match_name:
                    best_match = subject_names[best_match_name[0]]
                    teacher = best_match.get('teacher')
                    
                    if teacher:
                        combined_message = f"يدرس مادة {best_match['name']} الدكتور/ة {teacher}"
                    else:
                        combined_message = f"عذراً، لا تتوفر لدي معلومات عن مدرسي مادة {best_match['name']} حالياً"
                    
                    dispatcher.utter_message(text=combined_message)
                    
                    dispatcher.utter_message(response="utter_did_that_help")
                    return [SlotSet("subject", best_match['name'])]
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []

class ActionGetStudentGPA(Action):
    def name(self) -> Text:
        return "action_get_student_gpa"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.get_slot('metadata')
        
        if not metadata:
            metadata = tracker.get_slot('session_started_metadata')
            
        if not metadata:
            metadata = tracker.latest_message.get('metadata')
            
        if not metadata:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض معدلك التراكمي")
            return []
            
        token = metadata.get('token')
        
        if not token:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض معدلك التراكمي")
            return []
        
        try:
            decoded_token = jwt.decode(token, options={"verify_signature": False})
            student_id = decoded_token.get('id')
            
            if not student_id:
                dispatcher.utter_message(text="عذراً، حدث خطأ في التحقق من هويتك")
                return []
            
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f"{ENDPOINTS['get_student_by_id']}/{student_id}", headers=headers)
            
            if response.status_code == 200:
                student_data = response.json()
                gpa = student_data.get('gpa')
                name = f"{student_data.get('firstName', '')} {student_data.get('lastName', '')}"
                
                if gpa is not None:
                    gpa_formatted = "{:.2f}".format(gpa)
                    
                    gpa_class = ""
                    if gpa >= 3.7:
                        gpa_class = "ممتاز"
                    elif gpa >= 3.0:
                        gpa_class = "جيد جداً"
                    elif gpa >= 2.3:
                        gpa_class = "جيد"
                    elif gpa >= 2.0:
                        gpa_class = "مقبول"
                    else:
                        gpa_class = "تحت المراقبة الأكاديمية"
                    
                    message = f"مرحباً {name}،\nمعدلك التراكمي هو {gpa_formatted} ({gpa_class})"
                    dispatcher.utter_message(text=message)
                else:
                    dispatcher.utter_message(text="عذراً، لم نتمكن من العثور على معدلك التراكمي")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع معلومات المعدل التراكمي")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
