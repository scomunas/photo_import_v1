import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { StatusService, SystemStatus } from '../../services/status.service';
import { interval, Subscription } from 'rxjs';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.css'
})
export class SidebarComponent implements OnInit, OnDestroy {
  isCollapsed = false;
  status: SystemStatus = {
    status: 'checking',
    database: 'offline',
    nas: 'offline',
    version: '...'
  };
  private statusSub?: Subscription;

  constructor(private statusService: StatusService) {}

  ngOnInit() {
    this.checkStatus();
    // Refrescar cada 30 segundos
    this.statusSub = interval(30000).subscribe(() => this.checkStatus());
  }

  ngOnDestroy() {
    if (this.statusSub) {
      this.statusSub.unsubscribe();
    }
  }

  checkStatus() {
    this.statusService.getSystemStatus().subscribe(res => {
      this.status = res;
    });
  }

  toggleSidebar() {
    this.isCollapsed = !this.isCollapsed;
  }
}
