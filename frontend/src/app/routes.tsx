/** The route table (spec §8.1): Classic view's pages. F3 adds the office. */

import type { RouteObject } from 'react-router';

import { ClassicAgent } from '@/classic/ClassicAgent';
import { ClassicBrief } from '@/classic/ClassicBrief';
import { ClassicHome } from '@/classic/ClassicHome';
import { ClassicInbox } from '@/classic/ClassicInbox';
import { ClassicLayout } from '@/classic/ClassicLayout';
import { NotFound } from '@/classic/NotFound';

import { AppShell } from './AppShell';
import { HomeRedirect } from './HomeRedirect';
import { RouteError } from './RouteError';

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { path: '/', element: <HomeRedirect /> },
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
