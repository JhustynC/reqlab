import { Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-topbar',
  imports: [RouterLink, IconComponent],
  template: `
    <header class="topbar" [class.workspace-header]="!!projectName()">
      <div class="row grow">
        @if (projectName()) { <a class="icon-btn" routerLink="/projects" aria-label="Volver a proyectos"><app-icon name="back" /></a> }
        <a class="logo" routerLink="/projects" aria-label="Ir a proyectos"><span class="logo-symbol"><app-icon name="layers" /></span>ReqLab</a>
        <span class="sep"></span>
        @if (projectName()) { <h1 class="project-name">{{ projectName() }}</h1> }
        @else { <span class="muted desktop-only" style="font-size:12px">Laboratorio de requisitos</span> }
      </div>
      <div class="row">
        <span class="prototype">{{ projectName() ? 'PROYECTO ACTIVO' : 'APLICACIÓN WEB' }}</span>
        @if (!projectName()) {
          <button class="icon-btn" type="button" title="Configuración" aria-label="Abrir configuración" (click)="settingsRequested.emit()"><app-icon name="settings" /></button>
        }
      </div>
    </header>
  `,
})
export class TopbarComponent {
  readonly projectName = input('');
  readonly projectId = input('');
  readonly exportEnabled = input(false);
  readonly settingsRequested = output<void>();
}
