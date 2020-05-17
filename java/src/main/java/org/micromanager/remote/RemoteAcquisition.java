/*
 * To change this license header, choose License Headers in Project Properties.
 * To change this template file, choose Tools | Templates
 * and open the template in the editor.
 */
package org.micromanager.remote;

import mmcorej.org.json.JSONObject;
import org.micromanager.acqj.api.Acquisition;
import org.micromanager.acqj.api.AcquisitionInterface;
import org.micromanager.acqj.api.DataSink;
import org.micromanager.ndviewer.api.ViewerAcquisitionInterface;

/**
 * Class that serves as the java counterpart to a python acquisition
 *
 *
 * @author henrypinkard
 */
public class RemoteAcquisition extends Acquisition
        implements AcquisitionInterface, ViewerAcquisitionInterface {

   private RemoteEventSource eventSource_;

   public RemoteAcquisition(RemoteEventSource eventSource, RemoteAcquisitionSettings settings) {
      if (settings.dataLocation != null && settings.name != null) {
         dataSink_ = new RemoteViewerStorageAdapter(settings.showViewer, settings.dataLocation, settings.name);
      }
      initialize();
      eventSource_ = eventSource;
      eventSource.setAcquisition(this);
   }
   
   public int getEventPort() {
      return eventSource_.getPort();
   }
   
   @Override
   public void abort() {
      super.abort();
      eventSource_.abort();
   }
   
   @Override
   public void addToSummaryMetadata(JSONObject summaryMetadata) {

   }

   @Override
   public void addToImageMetadata(JSONObject tags) {

   }
    

}
