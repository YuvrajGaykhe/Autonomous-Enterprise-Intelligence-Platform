/**
 * The route table (spec §8.1): the office at `/` and `/brief/<id>`, under one parent so the 3D
 * world stays mounted between them, and Classic view's pages.
 */

import type { RouteObject } from 'react-router';

import { ClassicAgent } from '@/classic/ClassicAgent';
import { ClassicBrief } from '@/classic/ClassicBrief';
import { ClassicHome } from '@/classic/ClassicHome';
import { ClassicInbox } from '@/classic/ClassicInbox';
import { ClassicLayout } from '@/classic/ClassicLayout';
import { NotFound } from '@/classic/NotFound';

import { OfficePage } from '@/office/OfficePage';

import { AppShell } from './AppShell';
import { RouteError } from './RouteError';

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      {
        path: '/',
        element: <OfficePage />,
        children: [
          { index: true, element: null },
          { path: 'brief/:briefId', element: null },
        ],
      },
      {
        path: '/classic',
        element: <ClassicLayout />,
        children: [
          { index: true, element: <ClassicHome /> },
          { path: 'inbox', element: <ClassicInbox /> },
          { path: 'briefs/:briefId', element: <ClassicBrief /> },
          { path: 'agents/:agentId', element: <ClassicAgent /> },
        ],
      },
      { path: '*', element: <NotFound /> },
    ],
  },
];
