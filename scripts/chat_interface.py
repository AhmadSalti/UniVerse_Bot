import tkinter as tk
from tkinter import scrolledtext
import requests
import json

class ChatbotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ASPU AI Assistant")
        self.root.geometry("600x400")

        self.chat_display = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=50, height=20)
        self.chat_display.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

        self.input_field = tk.Entry(root, width=40)
        self.input_field.grid(row=1, column=0, padx=10, pady=10)

        self.send_button = tk.Button(root, text="Send", command=self.send_message)
        self.send_button.grid(row=1, column=1, padx=10, pady=10)

        self.input_field.bind("<Return>", lambda e: self.send_message())

    def send_message(self):
        user_message = self.input_field.get()
        if user_message.strip() == "":
            return

        self.chat_display.insert(tk.END, "You: " + user_message + "\n")
        
        responses = self.get_bot_response(user_message)
        
        for response in responses:
            self.chat_display.insert(tk.END, "Bot: " + response + "\n")
        
        self.chat_display.insert(tk.END, "\n")
        self.input_field.delete(0, tk.END)
        self.chat_display.see(tk.END)

    def get_bot_response(self, message):
        try:
            rasa_server_url = "http://localhost:5005/webhooks/rest/webhook"
            response = requests.post(
                rasa_server_url,
                json={"sender": "user", "message": message}
            )
            
            response_data = response.json()
            if response_data:
                return [msg['text'] for msg in response_data]
            return ["No response from bot"]
            
        except Exception as e:
            return [f"Error: {str(e)}"]

def main():
    root = tk.Tk()
    app = ChatbotGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()