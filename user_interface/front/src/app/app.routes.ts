import { Routes } from '@angular/router';
import { DashboardComponent } from './pages/dashboard/dashboard.component';
import { DetailsComponent } from './pages/details/details.component';
import { SettingsComponent } from './pages/settings/settings.component';

export const routes: Routes = [
  { path: 'dashboard', component: DashboardComponent },
  { path: 'changes', component: DetailsComponent },
  { path: 'configuration', component: SettingsComponent },
  { path: '', redirectTo: '/dashboard', pathMatch: 'full' }
];
