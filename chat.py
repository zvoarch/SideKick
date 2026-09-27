import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText


from gemini import ask_gemini


class GeminiChat:
    def __init__(self, root, ask_gemini):
        self.root = root
        self.ask_gemini = ask_gemini
        self.root.title("Gemini Chat")
        self.root.geometry("480x600")
        self.root.minsize(360, 420)

        self.history = ScrolledText(root, wrap=tk.WORD, state="disabled")
        self.history.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 8))

        input_row = tk.Frame(root)
        input_row.pack(fill=tk.X, padx=12, pady=(0, 12))

        self.prompt = tk.Entry(input_row)
        self.prompt.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.prompt.bind("<Return>", self.send_message)

        self.send_button = tk.Button(input_row, text="Send", command=self.send_message)
        self.send_button.pack(side=tk.LEFT, padx=(8, 0))

        self.append_message("Gemini", "Hi! I'm your personal assistant. What should we start working on?")
        self.prompt.focus_set()

    def append_message(self, speaker, message):
        self.history.configure(state="normal")
        self.history.insert(tk.END, f"{speaker}: {message}\n\n")
        self.history.see(tk.END)
        self.history.configure(state="disabled")

    def send_message(self, event=None):
        message = self.prompt.get().strip()
        if not message:
            return

        self.prompt.delete(0, tk.END)
        self.append_message("You", message)
        self.send_button.configure(state="disabled")
        self.prompt.configure(state="disabled")
        self.append_message("Gemini", "Thinking…")

        threading.Thread(target=self.get_response, args=(message,), daemon=True).start()

    def get_response(self, message):
        try:
            response = self.ask_gemini(message)
            response = response or "(Gemini returned an empty response.)"
        except Exception as error:
            response = f"Sorry, I couldn't get a response.\n{error}"

        self.root.after(0, self.show_response, response)

    def show_response(self, response):
        self.history.configure(state="normal")
        content = self.history.get("1.0", tk.END)
        marker = "Thinking…\n\n"
        position = content.rfind(marker)
        if position >= 0:
            start = f"1.0 + {position} chars"
            end = f"{start} + {len(marker)} chars"
            self.history.delete(start, end)
        self.history.insert(tk.END, f"Gemini: {response}\n\n")
        self.history.see(tk.END)
        self.history.configure(state="disabled")
        self.send_button.configure(state="normal")
        self.prompt.configure(state="normal")
        self.prompt.focus_set()


def main():
    root = tk.Tk()
    GeminiChat(root, ask_gemini)
    root.mainloop()


if __name__ == "__main__":
    main()



