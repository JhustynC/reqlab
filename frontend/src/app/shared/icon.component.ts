import { Component, input } from '@angular/core';

@Component({
  selector: 'app-icon',
  template: `
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      @switch (name()) {
        @case ('plus') { <path d="M12 5v14M5 12h14" /> }
        @case ('file') { <path d="M14 2H5v20h14V7l-5-5Z" /><path d="M14 2v6h5M8 12h8M8 16h6" /> }
        @case ('search') { <circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /> }
        @case ('arrow') { <path d="M4 12h16m-6-6 6 6-6 6" /> }
        @case ('back') { <path d="M20 12H4m6-6-6 6 6 6" /> }
        @case ('upload') { <path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" /> }
        @case ('check') { <path d="m5 12 4 4L19 6" /> }
        @case ('spark') { <path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3Z" /> }
        @case ('layers') { <path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /> }
        @case ('eye') { <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /> }
        @case ('download') { <path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5" /> }
        @case ('edit') { <path d="m15 4 5 5M4 20l5-1L21 7l-5-5L4 14v6Z" /> }
        @case ('history') { <path d="M3 10a9 9 0 1 1 1 7M3 3v7h7M12 7v5l3 2" /> }
        @case ('folder') { <path d="M3 5h7l2 3h9v12H3V5Z" /> }
        @case ('link') { <path d="m10 13 4-4m-5 6-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 2 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" /> }
        @case ('shield') { <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8 11 3 3 5-5" /> }
        @case ('chat') { <path d="M3 4h18v13H9l-6 4V4Z" /><path d="M7 9h10M7 13h6" /> }
        @case ('warning') { <path d="M12 3 2 21h20L12 3Z" /><path d="M12 9v5M12 17h.01" /> }
        @case ('book') { <path d="M3 3h6c2 0 3 2 3 2s1-2 3-2h6v17h-6c-2 0-3 1-3 1s-1-1-3-1H3V3ZM12 5v16" /> }
        @case ('settings') { <path d="M4 6h16M4 12h16M4 18h16" /><circle cx="8" cy="6" r="2" /><circle cx="16" cy="12" r="2" /><circle cx="10" cy="18" r="2" /> }
        @case ('trash') { <path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6" /> }
        @case ('archive') { <path d="M4 8v12h16V8M3 4h18v4H3zM9 12h6" /> }
        @case ('restore') { <path d="M4 8v12h16V8M3 4h18v4H3zM9 15h6M12 12v6" /> }
        @default { <circle cx="12" cy="12" r="8" /><path d="M9 12h6" /> }
      }
    </svg>
  `,
})
export class IconComponent { readonly name = input.required<string>(); }
