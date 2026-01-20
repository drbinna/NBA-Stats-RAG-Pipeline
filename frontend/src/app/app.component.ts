import { Component, OnDestroy, OnInit } from '@angular/core';
import { ChatService } from './services/chat.service';
import { environment } from '../environments/environment';

interface EvidenceItem {
  table: string;
  id: number;
}

interface Message {
  sender: 'user' | 'bot' | 'loading';
  text: string;
  evidence?: EvidenceItem[];
  isLoading?: boolean;
}

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Courtside - Thunder Fan Assist';
  messages: Message[] = [];
  userInput = '';
  showWelcome = true;
  carouselImages = [
    { src: 'assets/Oklahoma City GIF by OKC Thunder.gif', alt: 'OKC Thunder hype' },
    { src: 'assets/Russell Westbrook Lol GIF by NBA.gif', alt: 'Russell Westbrook energy' }
  ];
  currentSlide = 0;
  private carouselTimer: any;


  constructor(private chatService: ChatService) { }

  ngOnInit(): void {
    this.startCarousel();
  }

  ngOnDestroy(): void {
    if (this.carouselTimer) {
      clearInterval(this.carouselTimer);
    }
  }

  sendMessage(): void {
    const input = this.userInput.trim();
    if (!input) {
      return;
    }
    // Hide welcome message when user starts chatting
    if (this.showWelcome) {
      this.showWelcome = false;
    }
    this.messages.push({ sender: 'user', text: input });
    this.userInput = '';

    // Add loading message
    const loadingMessageIndex = this.messages.length;
    this.messages.push({ sender: 'loading', text: 'Thundering...', isLoading: true });

    this.chatService.sendMessage(input).subscribe({
      next: (res: any) => {
        // Replace loading message with actual response
        const reply = res?.answer ?? 'No Answer.';
        const evidence = Array.isArray(res?.evidence) ? res.evidence : [];
        this.messages[loadingMessageIndex] = { sender: 'bot', text: reply, evidence };
      },
      error: (err) => {
        // Replace loading message with error
        console.error('Chat Error:', err);
        const url = environment.apiUrl;
        this.messages[loadingMessageIndex] = {
          sender: 'bot',
          text: `Error contacting server at ${url}. Please verify the backend is running and the URL is correct.`
        };
      }
    });
  }

  goToSlide(index: number): void {
    this.currentSlide = index;
  }

  formatEvidence(evidence: EvidenceItem[] = []): string {
    if (!evidence.length) return '';
    const items = evidence.map(ev => `{ "table": "${ev.table}", "id": ${ev.id} }`);
    return `[ ${items.join(', ')} ]`;
  }

  isLoading(): boolean {
    return this.messages.some(m => m.isLoading);
  }

  private startCarousel(): void {
    if (this.carouselImages.length <= 1) {
      return;
    }

    this.carouselTimer = setInterval(() => {
      this.currentSlide = (this.currentSlide + 1) % this.carouselImages.length;
    }, 4500);
  }
}