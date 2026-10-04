import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, expect, it, vi } from 'vitest';
import { ListingEditHistory } from '@/components/listing-edit-history';
import { apiRequest } from '@/lib/api';
vi.mock('@/lib/api',()=>({apiRequest:vi.fn()}));
let root:ReturnType<typeof createRoot>|undefined;let container:HTMLDivElement|undefined;
afterEach(()=>{if(root)act(()=>root!.unmount());container?.remove();vi.resetAllMocks();});
it('loads original and changed safe values only when moderator opens history',async()=>{
 Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});container=document.createElement('div');document.body.append(container);root=createRoot(container);
 vi.mocked(apiRequest).mockResolvedValue({items:[{revision:4,reason:'seller_edit',from_status:'active',to_status:'draft',changed_field_keys:['price','contact_phone'],created_at:'2026-10-01T12:00:00Z',changes:[{field:'price',before:{amount:'10000.00',currency:'BYN'},after:{amount:'12000.00',currency:'BYN'}},{field:'contact_phone',before:'***1234',after:'***5678'}]}]});
 await act(async()=>{root!.render(<ListingEditHistory listingId='listing-1'/>);});
 expect(apiRequest).not.toHaveBeenCalled();
 await act(async()=>{container!.querySelector('button')!.click();});
 expect(apiRequest).toHaveBeenCalledWith('moderation/listings/listing-1/history');
 expect(container.textContent).toContain('10000.00 BYN');expect(container.textContent).toContain('12000.00 BYN');expect(container.textContent).toContain('***5678');expect(container.textContent).not.toContain('[object Object]');
});
it('keeps retry available after a history request failure',async()=>{
 Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});container=document.createElement('div');document.body.append(container);root=createRoot(container);vi.mocked(apiRequest).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({items:[]});
 await act(async()=>{root!.render(<ListingEditHistory listingId='listing-1'/>);});await act(async()=>{container!.querySelector('button')!.click();});expect(container.querySelector('[role=alert]')?.textContent).toContain('Не удалось');await act(async()=>{container!.querySelector('button')!.click();});expect(container.textContent).toContain('Правки пока не зафиксированы');
});
