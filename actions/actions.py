from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rapidfuzz import fuzz, process
import requests
import re
from .config import ENDPOINTS, OPENROUTER_API_KEY, OPENROUTER_URL
import os
from openai import OpenAI


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
                    total_hours = best_match.get('hours', 'غير محدد')
                    
                    t_section = best_match.get('TSection')
                    t_hours = t_section.get('t_hours', 0) if t_section else 0
                    
                    p_section = best_match.get('PSection')
                    p_hours = p_section.get('p_hours', 0) if p_section else 0
                    
                    if best_match.get('hasPractical', False):
                        message = f"عدد ساعات مادة {best_match['name']}:\n"
                        message += f"- إجمالي الساعات: {total_hours} ساعة\n"
                        message += f"- الساعات النظرية: {t_hours} ساعة\n"
                        message += f"- الساعات العملية: {p_hours} ساعة"
                    else:
                        message = f"عدد ساعات مادة {best_match['name']} هو {total_hours} ساعة"
                    
                    dispatcher.utter_message(text=message)
                    dispatcher.utter_message(response="utter_did_that_help")
                    return [SlotSet("subject", best_match['name'])]
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            print(f"Error in ActionGetSubjectHours: {str(e)}")
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
                
                subject_id_to_name = {str(s['id']): s['name'] for s in subjects}
                
                subject_names = {normalize_arabic_text(s['name']): s for s in subjects}
                best_match_name = process.extractOne(
                    normalized_input,
                    subject_names.keys(),
                    scorer=fuzz.WRatio,
                    score_cutoff=75
                )
                
                if best_match_name:
                    best_match = subject_names[best_match_name[0]]
                    prerequisites_id = best_match.get('prerequisitesId')
                    
                    prerequisite_names = []
                    
                    if prerequisites_id is not None:
                        if isinstance(prerequisites_id, list):
                            prereq_ids = prerequisites_id
                        else:
                            prereq_ids = [prerequisites_id]
                        
                        for prereq_id in prereq_ids:
                            if str(prereq_id) in subject_id_to_name:
                                prerequisite_names.append(subject_id_to_name[str(prereq_id)])
                    
                    if prerequisite_names:
                        prereq_list = "، ".join(prerequisite_names)
                        combined_message = f"متطلبات مادة {best_match['name']} هي: {prereq_list}"
                    else:
                        combined_message = f"لا توجد متطلبات سابقة لمادة {best_match['name']}"
                    
                    dispatcher.utter_message(text=combined_message)
                    dispatcher.utter_message(response="utter_did_that_help")
                    return [SlotSet("subject", best_match['name'])]
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            print(f"Error in ActionGetSubjectPrerequisites: {str(e)}")
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
            response = requests.get(f"{ENDPOINTS['get_all_subjects']}")
            
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
                    
                    if best_match.get('TSection') and best_match['TSection'].get('Teachers') and len(best_match['TSection']['Teachers']) > 0:
                        teacher_data = best_match['TSection']['Teachers'][0]
                        teacher_name = f"{teacher_data['User']['firstName']} {teacher_data['User']['lastName']}"
                        
                        message = f"يدرس مادة {best_match['name']} الدكتور/ة {teacher_name}"
                        dispatcher.utter_message(text=message)
                    else:
                        dispatcher.utter_message(text=f"عذراً، لا تتوفر معلومات عن مدرس مادة {best_match['name']}")
                    
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
        
        metadata = tracker.latest_message.get('metadata')
        
        if not metadata:
            metadata = tracker.get_slot('session_started_metadata')
            
        if not metadata:
            metadata = tracker.get_slot('metadata')
            
        if not metadata:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول كطالب أولاً لعرض معدلك التراكمي")
            return []
            
        student_id = metadata.get('student_id')
        
        if not student_id:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض معدلك التراكمي")
            return []
        
        try:
            response = requests.get(f"{ENDPOINTS['get_student_by_id']}/{student_id}")
            
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

class ActionGetStudentId(Action):
    def name(self) -> Text:
        return "action_get_student_id"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get('metadata')
        
        if not metadata:
            metadata = tracker.get_slot('session_started_metadata')
            
        if not metadata:
            metadata = tracker.get_slot('metadata')
            
        if not metadata:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض رقمك الجامعي")
            return []
            
        student_id = metadata.get('student_id')
        
        if not student_id:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض رقمك الجامعي")
            return []
        
        try:
            response = requests.get(f"{ENDPOINTS['get_student_by_id']}/{student_id}")
            
            if response.status_code == 200:
                student_data = response.json()
                name = f"{student_data.get('firstName', '')} {student_data.get('lastName', '')}"
                id_number = student_data.get('id')
                
                message = f"مرحباً {name}،\nرقمك الجامعي هو: {id_number}"
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع معلومات الرقم الجامعي")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetStudentHours(Action):
    def name(self) -> Text:
        return "action_get_student_hours"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get('metadata')
        
        if not metadata:
            metadata = tracker.get_slot('session_started_metadata')
            
        if not metadata:
            metadata = tracker.get_slot('metadata')
            
        if not metadata:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض عدد ساعاتك المنجزة")
            return []
            
        student_id = metadata.get('student_id')
        
        if not student_id:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض عدد ساعاتك المنجزة")
            return []
        
        try:
            response = requests.get(f"{ENDPOINTS['get_student_by_id']}/{student_id}")
            
            if response.status_code == 200:
                student_data = response.json()
                name = f"{student_data.get('firstName', '')} {student_data.get('lastName', '')}"
                hours = student_data.get('hoursAchieved', 0)
                
                message = f"مرحباً {name}،\nعدد الساعات المعتمدة المنجزة هو: {hours} ساعة"
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع معلومات الساعات المنجزة")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetStudentBalance(Action):
    def name(self) -> Text:
        return "action_get_student_balance"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get('metadata')
        
        if not metadata:
            metadata = tracker.get_slot('session_started_metadata')
            
        if not metadata:
            metadata = tracker.get_slot('metadata')
            
        if not metadata:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض رصيدك")
            return []
            
        student_id = metadata.get('student_id')
        
        if not student_id:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض رصيدك")
            return []
        
        try:
            response = requests.get(f"{ENDPOINTS['get_student_by_id']}/{student_id}")
            
            if response.status_code == 200:
                student_data = response.json()
                name = f"{student_data.get('firstName', '')} {student_data.get('lastName', '')}"
                balance = student_data.get('balance', 0)
                
                message = f"مرحباً {name}،\nرصيدك الحالي هو: {balance} ل.س"
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع معلومات الرصيد")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetEnrolledSubjects(Action):
    def name(self) -> Text:
        return "action_get_enrolled_subjects"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get('metadata')
        
        if not metadata:
            metadata = tracker.get_slot('session_started_metadata')
            
        if not metadata:
            metadata = tracker.get_slot('metadata')
            
        if not metadata:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض المواد المسجلة")
            return []
            
        student_id = metadata.get('student_id')
        
        if not student_id:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض المواد المسجلة")
            return []
        
        try:
            response = requests.get(f"{ENDPOINTS['get_student_enrollments']}/{student_id}/enrollment")
            
            if response.status_code == 200:
                enrollments = response.json()
                
                current_enrollments = [
                    enrollment for enrollment in enrollments 
                    if enrollment.get('status') == "Enrolled"
                ]
                
                if not current_enrollments:
                    dispatcher.utter_message(text="لا يوجد لديك مواد مسجلة في الفصل الحالي")
                    return []
                
                subject_names = [enrollment.get('subjectName', '') for enrollment in current_enrollments]
                
                message = "المواد المسجلة في الفصل الحالي:\n\n"
                for i, subject in enumerate(subject_names, 1):
                    message += f"{i}. {subject}\n"
                
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع معلومات المواد المسجلة")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetPassedSubjects(Action):
    def name(self) -> Text:
        return "action_get_passed_subjects"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get('metadata')
        
        if not metadata:
            metadata = tracker.get_slot('session_started_metadata')
            
        if not metadata:
            metadata = tracker.get_slot('metadata')
            
        if not metadata:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض المواد المنجزة")
            return []
            
        student_id = metadata.get('student_id')
        
        if not student_id:
            dispatcher.utter_message(text="عذراً، يجب عليك تسجيل الدخول أولاً لعرض المواد المنجزة")
            return []
        
        try:
            response = requests.get(f"{ENDPOINTS['get_student_enrollments']}/{student_id}/enrollment")
            
            if response.status_code == 200:
                enrollments = response.json()
                
                passed_subjects = [
                    enrollment for enrollment in enrollments 
                    if enrollment.get('status') == "Passed"
                ]
                
                if not passed_subjects:
                    dispatcher.utter_message(text="لم تنجح في أي مادة بعد")
                    return []
                
                subject_names = [subject.get('subjectName', '') for subject in passed_subjects]
                
                message = "المواد التي نجحت فيها:\n\n"
                for i, subject in enumerate(subject_names, 1):
                    message += f"{i}. {subject}\n"
                
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع معلومات المواد المنجزة")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetSubjectPracticalTeacher(Action):
    def name(self) -> Text:
        return "action_get_subject_practical_teacher"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        subject = next((entity['value'] for entity in tracker.latest_message.get('entities', []) 
                       if entity['entity'] == 'subject'), None)
        
        if not subject:
            subject = tracker.get_slot('subject')
            if not subject:
                dispatcher.utter_message(text="عذراً، لم تحدد المادة التي تريد معرفة مدرس الجلسات العملية لها. الرجاء ذكر اسم المادة")
                return []

        try:
            response = requests.get(f"{ENDPOINTS['get_all_subjects']}")
            
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
                    
                    if best_match.get('PSection') and best_match['PSection'].get('Teachers') and len(best_match['PSection']['Teachers']) > 0:
                        teacher_data = best_match['PSection']['Teachers'][0]
                        teacher_name = f"{teacher_data['User']['firstName']} {teacher_data['User']['lastName']}"
                        
                        message = f"يدرس الجلسات العملية لمادة {best_match['name']} الدكتور/ة {teacher_name}"
                        dispatcher.utter_message(text=message)
                    else:
                        dispatcher.utter_message(text=f"عذراً، لا تتوفر معلومات عن مدرس الجلسات العملية لمادة {best_match['name']}")
                    
                    dispatcher.utter_message(response="utter_did_that_help")
                    return [SlotSet("subject", best_match['name'])]
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetSubjectsByYear(Action):
    def name(self) -> Text:
        return "action_get_subjects_by_year"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        message = tracker.latest_message.get('text', '')
        
        year_mapping = {
            'الاولى': 1,
            'الثانية': 2,
            'الثالثة': 3,
            'الرابعة': 4,
            'الخامسة': 5
        }
        
        year = None
        
        for word in message.split():
            if word.isdigit() and 1 <= int(word) <= 5:
                year = int(word)
                break
        
        if not year:
            for arabic_year, num in year_mapping.items():
                if arabic_year in message:
                    year = num
                    break
        
        if not year:
            dispatcher.utter_message(text="عذراً، لم أفهم أي سنة تريد معرفة موادها. الرجاء تحديد السنة (من 1 إلى 5)")
            return []

        try:
            response = requests.get(f"{ENDPOINTS['get_all_subjects']}")
            
            if response.status_code == 200:
                subjects = response.json()
                
                year_subjects = [
                    subject for subject in subjects 
                    if subject.get('academicYear') == year
                ]
                
                if not year_subjects:
                    dispatcher.utter_message(text=f"عذراً، لا توجد مواد متوفرة للسنة {year}")
                    return []
                
                message = f"المواد المتوفرة في السنة {year}:\n\n"
                for i, subject in enumerate(year_subjects, 1):
                    message += f"{i}. {subject['name']}\n"
                
                dispatcher.utter_message(text=message)
                dispatcher.utter_message(response="utter_did_that_help")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع المعلومات")
        
        return []
    
class ActionGetLectureSchedule(Action):
    def name(self) -> Text:
        return "action_get_lecture_schedule"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        subject = next((entity['value'] for entity in tracker.latest_message.get('entities', []) 
                       if entity['entity'] == 'subject'), None)
        
        if not subject:
            subject = tracker.get_slot('subject')
            if not subject:
                dispatcher.utter_message(text="عذراً، لم تحدد المادة التي تريد معرفة جدول محاضراتها. الرجاء ذكر اسم المادة")
                return []

        try:
            # First get the subject to find its ID
            response = requests.get(ENDPOINTS["get_all_subjects"])
            
            if response.status_code == 200:
                subjects = response.json()
                normalized_input = normalize_arabic_text(subject)
                
                subject_names = {normalize_arabic_text(s['name']): s for s in subjects}
                
                best_match_name = get_best_subject_match(normalized_input, subject_names)
                
                if best_match_name:
                    best_match = subject_names[best_match_name[0]]
                    subject_id = best_match['id']
                    
                    # Now get lectures for this subject
                    lectures_response = requests.get(f"{ENDPOINTS['get_lectures']}?subject={best_match['name']}")
                    
                    if lectures_response.status_code == 200:
                        lectures = lectures_response.json()
                        
                        if not lectures:
                            dispatcher.utter_message(text=f"عذراً، لا توجد محاضرات مسجلة لمادة {best_match['name']} في الوقت الحالي")
                            return [SlotSet("subject", best_match['name'])]
                        
                        # Format the response
                        message = f"جدول محاضرات مادة {best_match['name']}:\n\n"
                        
                        for i, lecture in enumerate(lectures, 1):
                            day = lecture.get('day', 'غير محدد')
                            start_time = lecture.get('start_time', 'غير محدد')
                            end_time = lecture.get('end_time', 'غير محدد')
                            groups = lecture.get('groups', [])
                            
                            # Extract room information from nested object
                            room_info = lecture.get('Room', {})
                            room_number = room_info.get('number', 'غير محدد')
                            room_floor = room_info.get('floor', 'غير محدد')
                            
                            # Extract teacher information from nested object
                            teacher_info = lecture.get('Teacher', {})
                            user_info = teacher_info.get('User', {})
                            teacher_first_name = user_info.get('firstName', 'غير محدد')
                            teacher_last_name = user_info.get('lastName', 'غير محدد')
                            teacher_name = f"{teacher_first_name} {teacher_last_name}"
                            
                            message += f"{i}. اليوم: {day}\n"
                            message += f"   الوقت: {start_time} - {end_time}\n"
                            message += f"   القاعة: {room_number} (الطابق {room_floor})\n"
                            message += f"   المدرس: {teacher_name}\n"
                            if groups:
                                message += f"   الفئة: {', '.join(map(str, groups))}\n"
                            message += "\n"
                        
                        dispatcher.utter_message(text=message)
                        dispatcher.utter_message(response="utter_did_that_help")
                        return [SlotSet("subject", best_match['name'])]
                    else:
                        dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع جدول المحاضرات")
                else:
                    dispatcher.utter_message(text=f"عذراً، لا يوجد لدي معلومات عن مادة {subject}")
            else:
                dispatcher.utter_message(text="عذراً، حدث خطأ في الاتصال بقاعدة البيانات")
                
        except Exception as e:
            print(f"Error in ActionGetLectureSchedule: {str(e)}")
            dispatcher.utter_message(text="عذراً، حدث خطأ في استرجاع معلومات جدول المحاضرات")
        
        return []

class ActionLLMFallback(Action):
    def name(self) -> Text:
        return "action_llm_fallback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        message = tracker.latest_message.get('text', '')
        intent_ranking = tracker.latest_message.get('intent_ranking', [])
        
        explanation_keywords = ["شرح", "اشرح", "اشرحلي", "شرح لي", "شرح لنا", "اشرح لنا", "شرح عن", "اشرح عن", "شرح حول", "اشرح حول", "تشرح", "تشرحلي"]
        example_keywords = ["مثال", "امثلة", "مثال على", "امثلة على", "مثال عن", "امثلة عن", "مثال حول", "امثلة حول", "مثال تطبيقي", "امثلة تطبيقية"]
        advice_keywords = ["نصيحة", "نصائح", "نصيحتك", "نصائحك", "نصيحة حول", "نصائح حول", "نصيحة عن", "نصائح عن", "كيف", "كيفية", "كيف يمكن", "كيف يمكنني"]
        comparison_keywords = ["مقارنة", "قارن", "قارني", "قارن بين", "قارني بين", "الفرق بين", "ما الفرق بين", "ما هو الفرق بين"]
        definition_keywords = ["تعريف", "تعريفات", "ما هو", "ما هي", "ما معنى", "ما المقصود بـ", "ما المقصود من"]
        study_keywords = ["دراسة", "مذاكرة", "تحضير", "امتحان", "اختبار", "واجب", "مشروع", "بحث", "تقرير", "عرض", "محاضرة", "درس", "دروس", "منهاج", "مناهج", "مقرر", "مقررات", "ساعات", "ساعة", "معدل", "علامة", "علامات", "نقطة", "نقاط", "تراكمي", "تراكمية", "فصل", "فصول", "سنة", "سنوات", "عام", "أعوام", "جامعة", "جامعي", "جامعية", "كلية", "كليات", "قسم", "أقسام", "شعبة", "شعب", "مجموعة", "مجموعات", "معمل", "معامل", "مختبر", "مختبرات", "تدريب", "تدريبات", "تدريبي", "تدريبية", "عملي", "عملية", "نظري", "نظرية", "محاضرة", "محاضرات", "تمرين", "تمارين", "واجب", "واجبات", "مشروع", "مشاريع", "بحث", "أبحاث", "تقرير", "تقارير", "عرض", "عروض", "مناقشة", "مناقشات", "ندوة", "ندوات", "ورشة", "ورش", "سيمنار", "سيمنارات", "مؤتمر", "مؤتمرات", "دورة", "دورات"]
        academic_keywords = ["أكاديمي", "أكاديمية", "تعليمي", "تعليمية", "تربوي", "تربوية", "تعليم", "تدريس", "تعلم", "تعليم", "تدريب", "تدريبي", "تدريبية", "عملي", "عملية", "نظري", "نظرية", "محاضرة", "محاضرات", "تمرين", "تمارين", "واجب", "واجبات", "مشروع", "مشاريع", "بحث", "أبحاث", "تقرير", "تقارير", "عرض", "عروض", "مناقشة", "مناقشات", "ندوة", "ندوات", "ورشة", "ورش", "سيمنار", "سيمنارات", "مؤتمر", "مؤتمرات", "دورة", "دورات"]
        programming_keywords = [
            # Programming Languages
            "python", "بايثون", "جافا", "java", "javascript", "جافاسكريبت", "c++", "سي بلس بلس", "c#", "سي شارب",
            "php", "بي اتش بي", "ruby", "روبي", "swift", "سويفت", "kotlin", "كوتلن", "go", "غو",
            "rust", "رست", "typescript", "تايبسكريبت", "scala", "سكالا", "perl", "بيرل",
            
            # Programming Concepts
            "برمجة", "programming", "كود", "code", "خوارزمية", "algorithm", "دالة", "function",
            "متغير", "variable", "شرط", "condition", "حلقة", "loop", "مصفوفة", "array",
            "كائن", "object", "class", "كلاس", "وراثة", "inheritance", "تغليف", "encapsulation",
            "تعدد", "polymorphism", "واجهة", "interface", "استثناء", "exception", "خطأ", "error",
            "تصحيح", "debug", "اختبار", "test", "تطوير", "development", "تطبيق", "application",
            "موقع", "website", "واجهة", "frontend", "خلفية", "backend", "قاعدة بيانات", "database",
            "sql", "اس كيو ال", "nosql", "نو اس كيو ال", "api", "اي بي اي", "rest", "رست",
            "graphql", "جراف كيو ال", "docker", "دوكر", "kubernetes", "كوبرنيتس", "git", "جيت",
            "github", "جيت هب", "devops", "ديفوبس", "ci/cd", "سي اي سي دي", "agile", "اجايل",
            "scrum", "سكرام", "kanban", "كانبان", "microservices", "مايكروسيرفيس", "serverless", "سيرفرلس"
        ]
        study_plan_keywords = [
            # Study Plan Related
            "خطة", "خطة دراسية", "خطة تعليمية", "منهج", "منهاج", "مقرر", "مقررات",
            "تعلم", "تعليم", "دراسة", "مذاكرة", "تحضير", "استعداد", "تجهيز",
            "كيف اتعلم", "كيف ادرس", "كيف ابدأ", "كيف ابدأ تعلم", "كيف ابدأ دراسة",
            "خطوات", "مراحل", "مرحلة", "مرحلة تعليمية", "مرحلة دراسية",
            "محتوى", "محتويات", "مواضيع", "موضوع", "فصول", "فصل",
            "مصادر", "مصدر", "مراجع", "مرجع", "كتب", "كتاب", "دورات", "دورة",
            "تطبيق", "تطبيقات", "تمارين", "تمرين", "مشاريع", "مشروع",
            "جدول", "جدول زمني", "مواعيد", "موعد", "فترة", "فترات",
            "مستوى", "مستويات", "مبتدئ", "متوسط", "متقدم", "محترف",
            "تقييم", "تقييم ذاتي", "اختبار", "اختبارات", "امتحان", "امتحانات",
            "متابعة", "تتبع", "تقدم", "تطور", "تحسين", "تطوير",
            "استراتيجية", "استراتيجيات", "طريقة", "طرق", "اسلوب", "اساليب",
            "نصائح", "نصيحة", "ارشادات", "ارشاد", "توجيه", "توجيهات",
            "موارد", "مورد", "ادوات", "اداة", "برامج", "برنامج",
            "community", "مجتمع", "منتدى", "منتديات", "مجموعة", "مجموعات",
            "mentor", "مرشد", "مدرب", "معلم", "استاذ", "دكتور",
            "roadmap", "خريطة طريق", "مسار", "مسارات", "طريق", "طرق", "اريد خطة"
        ]
        
        is_explanation_request = any(keyword in message.lower() for keyword in explanation_keywords)
        is_example_request = any(keyword in message.lower() for keyword in example_keywords)
        is_advice_request = any(keyword in message.lower() for keyword in advice_keywords)
        is_comparison_request = any(keyword in message.lower() for keyword in comparison_keywords)
        is_definition_request = any(keyword in message.lower() for keyword in definition_keywords)
        is_study_request = any(keyword in message.lower() for keyword in study_keywords)
        is_academic_request = any(keyword in message.lower() for keyword in academic_keywords)
        is_programming_request = any(keyword in message.lower() for keyword in programming_keywords)
        is_study_plan_request = any(keyword in message.lower() for keyword in study_plan_keywords)
        
        if intent_ranking:
            top_intent = intent_ranking[0]
            confidence = top_intent.get('confidence', 0)
            intent_name = top_intent.get('name', '')
            
            has_special_keywords = (
                is_programming_request or 
                is_study_plan_request or 
                is_explanation_request or 
                is_example_request or 
                is_advice_request or 
                is_comparison_request or 
                is_definition_request
            )
            
            if not has_special_keywords and confidence > 0.7 and intent_name != 'nlu_fallback':
                return []
        
        try:
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=OPENROUTER_API_KEY
            )
            
            prompt = f"""You are an academic assistant for a university specializing in IT and Computer Science. The user asked: "{message}"

Based on the type of request, provide an appropriate response:
- For explanations: Provide detailed and educational explanations
- For examples: Provide clear, practical examples that illustrate the concept
- For advice: Provide practical and actionable advice
- For comparisons: Provide detailed comparisons highlighting key differences and similarities
- For definitions: Provide clear and concise definitions with additional context
- For emotional support: Provide empathetic and motivational responses
- For academic struggles: Provide supportive advice and practical solutions
- For programming questions: Provide detailed technical explanations with code examples when appropriate
- For study plans: Provide structured learning paths with clear milestones and resources

If the topic is related to:
- IT and Computer Science topics (programming, cybersecurity, networks, AI, etc.)
- Technology and software development
- Academic research and studies
- Mathematics
- Life advice
- Mental health
- Student emotional well-being (boredom, stress, motivation, etc.)
- Academic challenges and struggles
- Study-related concerns
- Programming languages and concepts
- Learning paths and study plans
Provide a helpful and detailed response.

If the topic is not related to any of these areas, respond with:
"عذراً، أنا مساعد أكاديمي متخصص في مجال تقانة المعلومات وعلوم الحاسوب. يمكنني مساعدتك في الأسئلة المتعلقة بالجامعة والمواد الدراسية والمناهج الأكاديمية وتقانة المعلومات. هل لديك أي سؤال متعلق بهذه المواضيع؟"

Please respond in formal Arabic with a polite tone.
Don't repeat to the user that you are an academic assistant, just respond to the user's question.
It's extremely important to respond in Arabic, especially if the question is in Arabic. If it's in English, you can respond in English but let the user know that this bot is designed for Arabic responses.

For programming questions:
- Provide clear explanations of concepts
- Include code examples when relevant
- Explain best practices and common pitfalls
- Suggest relevant resources for further learning
- If the question is about a specific programming language, focus on that language's syntax and conventions

For study plans:
- Provide a structured learning path with clear milestones
- Include recommended resources (books, courses, websites)
- Suggest practical exercises and projects
- Include time estimates for each phase
- Recommend assessment methods to track progress
- Consider the student's current level and goals
- Include both theoretical and practical components
- Suggest community resources and support systems"""

            completion = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://github.com/cheahjs/free-llm-api-resources",
                    "X-Title": "UniVerse Bot"
                },
                model="deepseek/deepseek-chat-v3-0324:free",
                messages=[
                    {"role": "system", "content": "You are a helpful academic assistant specializing in IT and Computer Science that responds in Arabic."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = completion.choices[0].message.content
            dispatcher.utter_message(text=response_text)
            
        except Exception as e:
            print(f"Error in ActionLLMFallback: {str(e)}")
            if any(term in message.lower() for term in ["university", "academic", "study", "computer", "it", "programming", "cybersecurity", "network", "software"]):
                dispatcher.utter_message(text="عذراً، أنا مساعد أكاديمي متخصص في مجال تقانة المعلومات وعلوم الحاسوب. يمكنني مساعدتك في الأسئلة المتعلقة بالجامعة والمواد الدراسية والمناهج الأكاديمية وتقانة المعلومات. هل لديك أي سؤال متعلق بهذه المواضيع؟")
            else:
                dispatcher.utter_message(text="عذراً، أنا مساعد أكاديمي متخصص في مجال تقانة المعلومات وعلوم الحاسوب. يمكنني مساعدتك في الأسئلة المتعلقة بالجامعة والمواد الدراسية والمناهج الأكاديمية وتقانة المعلومات. هل لديك أي سؤال متعلق بهذه المواضيع؟")
        
        return []
    
        