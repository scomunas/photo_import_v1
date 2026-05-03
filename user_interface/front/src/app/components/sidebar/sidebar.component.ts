import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { StatusService, SystemStatus } from '../../services/status.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.css'
})
export class SidebarComponent implements OnInit {
  isCollapsed = false;
  status: SystemStatus = {
    status: 'checking',
    database: 'offline',
    nas: 'offline',
    version: '...'
  };

  constructor(private statusService: StatusService) {}

  ngOnInit() {
    this.checkStatus();
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
