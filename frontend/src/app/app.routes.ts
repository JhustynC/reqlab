import { Routes } from '@angular/router';
import { ProjectListComponent } from './features/projects/project-list.component';
import { WorkspaceComponent } from './features/workspace/workspace.component';

export const routes: Routes = [
  { path: 'projects', component: ProjectListComponent, title: 'Proyectos · ReqLab' },
  { path: 'projects/:id/:phase', component: WorkspaceComponent, title: 'Espacio de trabajo · ReqLab' },
  { path: '', pathMatch: 'full', redirectTo: 'projects' },
  { path: '**', redirectTo: 'projects' },
];
