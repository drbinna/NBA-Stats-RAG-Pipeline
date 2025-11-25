import { Component } from '@angular/core';
import { ChatService } from './services/chat.service';

interface Message {
  sender: 'user' | 'bot';
  text: string;
}

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent {
  title = 'AI Engineering Sandbox';
  messages: Message[] = [];
  userInput = '';


  constructor(private chatService: ChatService) {}

  sendMessage(): void {
    const input = this.userInput.trim();
    if (!input) {
      return;
    }
    this.messages.push({ sender: 'user', text: input });
    this.userInput = '';
    this.chatService.sendMessage(input).subscribe({
      next: (res: any) => {
        const reply = res?.answer ?? 'No Answer.';
        this.messages.push({ sender: 'bot', text: reply });
      },
      error: () => {
        this.messages.push({ sender: 'bot', text: 'Error contacting server.' });
      }
    });
  }
}